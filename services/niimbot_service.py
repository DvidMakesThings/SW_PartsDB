"""
services.niimbot_service - Niimbot B1 Bluetooth label printer integration.

Supports printing labels directly to Niimbot B1/B18/B21 thermal printers via BLE.
Protocol based on reverse-engineered Niimbot communication.
"""

import abc
import asyncio
import enum
import logging
import struct
import time
import threading
from io import BytesIO
from typing import Optional, Dict, List, Callable

from PIL import Image

logger = logging.getLogger(__name__)


# =============================================================================
# Packet Protocol
# =============================================================================

class NiimbotPacket:
    """
    Niimbot packet format:
    [0x55 0x55] [type] [len] [data...] [checksum] [0xAA 0xAA]
    """
    def __init__(self, type_: int, data: bytes):
        self.type = type_
        self.data = data

    @classmethod
    def from_bytes(cls, pkt: bytes) -> "NiimbotPacket":
        if len(pkt) < 7 or pkt[:2] != b"\x55\x55" or pkt[-2:] != b"\xaa\xaa":
            raise ValueError(f"Invalid packet format: {pkt.hex()}")
        
        type_ = pkt[2]
        len_ = pkt[3]
        data = pkt[4:4 + len_]
        
        checksum = type_ ^ len_
        for b in data:
            checksum ^= b
        
        if checksum != pkt[-3]:
            raise ValueError(f"Checksum mismatch: expected {checksum}, got {pkt[-3]}")
        
        return cls(type_, data)

    def to_bytes(self) -> bytes:
        checksum = self.type ^ len(self.data)
        for b in self.data:
            checksum ^= b
        return bytes([0x55, 0x55, self.type, len(self.data), *self.data, checksum, 0xAA, 0xAA])

    def __repr__(self):
        return f"<NiimbotPacket type=0x{self.type:02x} data={self.data.hex()}>"


class RequestCode(enum.IntEnum):
    """Niimbot command codes."""
    GET_INFO = 0x40
    GET_RFID = 0x1A
    HEARTBEAT = 0xDC
    SET_LABEL_TYPE = 0x23
    SET_LABEL_DENSITY = 0x21
    START_PRINT = 0x01
    END_PRINT = 0xF3
    START_PAGE_PRINT = 0x03
    END_PAGE_PRINT = 0xE3
    SET_PAGE_SIZE = 0x13
    SET_QUANTITY = 0x15
    GET_PRINT_STATUS = 0xA3
    PRINT_BITMAP_ROW = 0x85
    PRINT_BITMAP_ROW_INDEXED = 0x83


class PrinterInfo(enum.IntEnum):
    """Printer info request types."""
    DENSITY = 1
    PRINT_SPEED = 2
    LABEL_TYPE = 3
    DEVICE_TYPE = 8
    SOFTWARE_VERSION = 9
    BATTERY = 10
    DEVICE_SERIAL = 11
    HARDWARE_VERSION = 12


# =============================================================================
# Bluetooth Transport
# =============================================================================

class NiimbotTransport:
    """BLE transport for Niimbot printers using bleak."""
    
    def __init__(self, address: str):
        self._address = address
        self._client = None
        self._char_uuid = None
        self._notification_event: Optional[asyncio.Event] = None
        self._notification_data: Optional[bytes] = None
        self._connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
    
    def connect(self) -> bool:
        """Connect to the Niimbot printer. Returns True on success."""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._async_connect())
                self._loop.run_forever()
            except Exception as e:
                logger.error(f"BLE connection error: {e}")
        
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        
        # Wait for connection
        timeout = 15.0
        elapsed = 0.0
        while not self._connected and elapsed < timeout:
            time.sleep(0.1)
            elapsed += 0.1
        
        if not self._connected:
            logger.error(f"Connection timeout to {self._address}")
            return False
        
        logger.info(f"Connected to Niimbot at {self._address}")
        return True
    
    async def _async_connect(self):
        """Async BLE connection."""
        from bleak import BleakClient
        
        self._client = BleakClient(self._address)
        await self._client.connect()
        
        # Request larger MTU for better throughput (default is often 23 bytes)
        try:
            mtu = await self._client.mtu_size
            logger.info(f"BLE MTU size: {mtu}")
        except Exception:
            pass
        
        await asyncio.sleep(0.3)
        
        # Find the printer characteristic
        for service in self._client.services:
            for char in service.characteristics:
                props = char.properties
                if 'read' in props and 'write-without-response' in props and 'notify' in props:
                    self._char_uuid = char.uuid
                    break
            if self._char_uuid:
                break
        
        if not self._char_uuid:
            raise ConnectionError("Could not find Niimbot BLE characteristic")
        
        self._connected = True
        logger.info(f"BLE connected, characteristic: {self._char_uuid}")
    
    def _notification_handler(self, sender, data: bytes):
        """Handle BLE notifications."""
        self._notification_data = data
        if self._notification_event:
            self._notification_event.set()
    
    async def _send_command(self, code: int, data: bytes, timeout: float = 5.0) -> Optional[NiimbotPacket]:
        """Send command and wait for response."""
        if not self._client or not self._client.is_connected:
            raise ConnectionError("Not connected")
        
        packet = NiimbotPacket(code, data)
        self._notification_event = asyncio.Event()
        
        await self._client.start_notify(self._char_uuid, self._notification_handler)
        await self._client.write_gatt_char(self._char_uuid, packet.to_bytes())
        
        try:
            await asyncio.wait_for(self._notification_event.wait(), timeout)
            response = NiimbotPacket.from_bytes(self._notification_data)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for response to command 0x{code:02x}")
            response = None
        finally:
            await self._client.stop_notify(self._char_uuid)
            self._notification_event = None
        
        return response
    
    async def _write_raw(self, packet: NiimbotPacket):
        """Write packet without waiting for response (fire-and-forget for speed)."""
        if not self._client or not self._client.is_connected:
            raise ConnectionError("Not connected")
        # Use response=False for write-without-response (much faster for bulk data)
        await self._client.write_gatt_char(self._char_uuid, packet.to_bytes(), response=False)
    
    def run_async(self, coro):
        """Run async coroutine in the BLE thread."""
        if not self._loop:
            raise ConnectionError("BLE loop not available")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=60)
    
    def disconnect(self):
        """Disconnect from the printer."""
        if self._client and self._connected:
            try:
                if self._loop and not self._loop.is_closed():
                    future = asyncio.run_coroutine_threadsafe(self._client.disconnect(), self._loop)
                    future.result(timeout=5)
                    self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception as e:
                logger.error(f"Disconnect error: {e}")
        self._connected = False
        logger.info("Disconnected from Niimbot")


# =============================================================================
# Printer Client
# =============================================================================

class NiimbotPrinter:
    """High-level interface to Niimbot printer."""
    
    # Model specs: max width in pixels
    MODEL_SPECS = {
        "b1": 384,
        "b18": 384,
        "b21": 384,
        "d11": 96,
        "d110": 96,
    }
    
    def __init__(self, transport: NiimbotTransport, model: str = "b1"):
        self._transport = transport
        self._model = model.lower()
        self._max_width = self.MODEL_SPECS.get(self._model, 384)
    
    def close(self):
        """Close connection."""
        self._transport.disconnect()
    
    def print_image(self, image: Image.Image, density: int = 3, copies: int = 1,
                    progress_callback: Optional[Callable[[int, int], None]] = None):
        """
        Print an image to the label printer.
        
        Args:
            image: PIL Image to print (will be converted to 1-bit)
            density: Print density 1-5 (default 3)
            copies: Number of copies
            progress_callback: Optional callback(current_row, total_rows)
        """
        if image.width > self._max_width:
            raise ValueError(f"Image width {image.width}px exceeds max {self._max_width}px for {self._model}")
        
        # Clamp density for certain models
        if self._model in ("b18", "d11", "d110") and density > 3:
            density = 3
        
        logger.info(f"Starting print: {image.width}x{image.height}px, density={density}, copies={copies}")
        self._transport.run_async(self._async_print(image, density, copies, progress_callback))
        logger.info("Print complete")
    
    async def _async_print(self, image: Image.Image, density: int, copies: int,
                          progress_callback: Optional[Callable[[int, int], None]]):
        """Async print sequence."""
        try:
            # 1. Set density
            await self._set_density(density)
            await asyncio.sleep(0.02)
            
            # 2. Set label type (1 = gap label)
            await self._set_label_type(1)
            await asyncio.sleep(0.02)
            
            # 3. Start print job
            await self._start_print(copies)
            await asyncio.sleep(0.02)
            
            # 4. Start page
            await self._start_page()
            await asyncio.sleep(0.02)
            
            # 5. Set page dimensions
            await self._set_page_size(image.height, image.width, copies)
            await asyncio.sleep(0.02)
            
            # 6. Send image rows (minimal delays for speed)
            total_rows = image.height
            row_num = 0
            for packet in self._encode_image(image, threshold=180):
                await self._transport._write_raw(packet)
                row_num += 1
                if progress_callback and row_num % 50 == 0:
                    progress_callback(row_num, total_rows)
                # Tiny yield to prevent blocking - no real delay needed with write-without-response
                if row_num % 8 == 0:
                    await asyncio.sleep(0)
            
            if progress_callback:
                progress_callback(total_rows, total_rows)
            
            # 7. End page (with retry)
            for _ in range(10):
                if await self._end_page():
                    break
                await asyncio.sleep(0.05)
            
            # 8. Wait for print completion
            for _ in range(100):  # Max ~10s wait
                status = await self._get_status()
                if status.get("page", 0) >= copies:
                    break
                await asyncio.sleep(0.1)
            
            # 9. End print
            await self._end_print()
            
        except Exception as e:
            logger.error(f"Print error: {e}")
            try:
                await self._end_print()
            except:
                pass
            raise
    
    def _encode_image(self, image: Image.Image, threshold: int = 180):
        """Convert image to Niimbot packet stream."""
        # Convert to 1-bit monochrome
        # Higher threshold = more black pixels = darker print
        img = image.convert("L")
        img = img.point(lambda x: 0 if x < threshold else 255, '1')
        
        for y in range(img.height):
            # Build row as bit array (1 = black)
            row_bits = []
            for x in range(img.width):
                pixel = img.getpixel((x, y))
                row_bits.append(1 if pixel == 0 else 0)  # 0 in 1-bit = black
            
            # Pad to printhead width
            while len(row_bits) < self._max_width:
                row_bits.append(0)
            
            # Convert to bytes (MSB first)
            row_bytes = []
            for i in range(0, len(row_bits), 8):
                byte_val = 0
                for j in range(8):
                    if i + j < len(row_bits) and row_bits[i + j]:
                        byte_val |= (1 << (7 - j))
                row_bytes.append(byte_val)
            
            row_data = bytes(row_bytes)
            black_count = sum(row_bits)
            
            # Count pixels for packet header
            counts = self._count_pixels(row_data)
            
            # Use indexed packet for sparse rows (≤6 black pixels)
            if black_count <= 6:
                yield self._make_indexed_packet(y, 1, row_data)
            else:
                yield self._make_bitmap_packet(y, 1, row_data, counts)
    
    def _count_pixels(self, data: bytes) -> tuple:
        """Count black pixels for packet header."""
        total = sum(bin(b).count('1') for b in data)
        return (0, total & 0xFF, (total >> 8) & 0xFF)
    
    def _make_bitmap_packet(self, row: int, repeats: int, data: bytes, counts: tuple) -> NiimbotPacket:
        """Create regular bitmap row packet."""
        payload = struct.pack(">H", row) + bytes(counts) + bytes([repeats]) + data
        return NiimbotPacket(RequestCode.PRINT_BITMAP_ROW, payload)
    
    def _make_indexed_packet(self, row: int, repeats: int, data: bytes) -> NiimbotPacket:
        """Create indexed bitmap row packet for sparse data."""
        counts = self._count_pixels(data)
        
        # Build index of black pixel positions
        indexes = []
        for byte_pos, byte_val in enumerate(data):
            for bit_pos in range(8):
                if byte_val & (1 << (7 - bit_pos)):
                    pixel_pos = byte_pos * 8 + bit_pos
                    indexes.extend([(pixel_pos >> 8) & 0xFF, pixel_pos & 0xFF])
        
        payload = struct.pack(">H", row) + bytes(counts) + bytes([repeats]) + bytes(indexes)
        return NiimbotPacket(RequestCode.PRINT_BITMAP_ROW_INDEXED, payload)
    
    # Command helpers
    async def _set_density(self, n: int) -> bool:
        pkt = await self._transport._send_command(RequestCode.SET_LABEL_DENSITY, bytes([n]))
        return pkt and bool(pkt.data[0]) if pkt else False
    
    async def _set_label_type(self, n: int) -> bool:
        pkt = await self._transport._send_command(RequestCode.SET_LABEL_TYPE, bytes([n]))
        return pkt and bool(pkt.data[0]) if pkt else False
    
    async def _start_print(self, total_pages: int) -> bool:
        data = struct.pack(">H", total_pages) + b"\x00\x00\x00\x00\x00"
        pkt = await self._transport._send_command(RequestCode.START_PRINT, data)
        return pkt and bool(pkt.data[0]) if pkt else False
    
    async def _end_print(self) -> bool:
        pkt = await self._transport._send_command(RequestCode.END_PRINT, b"\x01")
        return pkt and bool(pkt.data[0]) if pkt else False
    
    async def _start_page(self) -> bool:
        pkt = await self._transport._send_command(RequestCode.START_PAGE_PRINT, b"\x01")
        return pkt and bool(pkt.data[0]) if pkt else False
    
    async def _end_page(self) -> bool:
        pkt = await self._transport._send_command(RequestCode.END_PAGE_PRINT, b"\x01")
        return pkt and bool(pkt.data[0]) if pkt else False
    
    async def _set_page_size(self, rows: int, cols: int, copies: int) -> bool:
        data = struct.pack(">HHH", rows, cols, copies)
        pkt = await self._transport._send_command(RequestCode.SET_PAGE_SIZE, data)
        return pkt and bool(pkt.data[0]) if pkt else False
    
    async def _get_status(self) -> dict:
        pkt = await self._transport._send_command(RequestCode.GET_PRINT_STATUS, b"\x01")
        if pkt and len(pkt.data) >= 2:
            page = struct.unpack(">H", pkt.data[:2])[0]
            return {"page": page}
        return {"page": 0}


# =============================================================================
# Scanner
# =============================================================================

class NiimbotScanner:
    """Scanner to find Niimbot BLE devices."""
    
    @staticmethod
    async def scan_async(name_filter: str = "B1", timeout: float = 10.0) -> List[Dict]:
        """Scan for Niimbot devices asynchronously."""
        from bleak import BleakScanner
        
        devices = await BleakScanner.discover(timeout=timeout)
        results = []
        
        for dev in devices:
            if dev.name and name_filter.lower() in dev.name.lower():
                results.append({
                    "name": dev.name,
                    "address": dev.address,
                    "rssi": getattr(dev, "rssi", None)
                })
        
        return results
    
    @staticmethod
    def scan(name_filter: str = "B1", timeout: float = 10.0) -> List[Dict]:
        """Synchronous scan for Niimbot devices."""
        import concurrent.futures
        
        def do_scan():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(NiimbotScanner.scan_async(name_filter, timeout))
            finally:
                loop.close()
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(do_scan)
            return future.result(timeout=timeout + 5)


# =============================================================================
# Convenience Functions
# =============================================================================

def svg_to_image(svg_content: str, dpi: int = 203) -> Image.Image:
    """
    Convert SVG content to PIL Image suitable for thermal printing.
    
    Niimbot B1 has 203 DPI (8 dots/mm).
    50x30mm label = 400x240 pixels
    """
    import cairosvg
    
    # Render SVG to PNG bytes
    png_data = cairosvg.svg2png(
        bytestring=svg_content.encode('utf-8'),
        dpi=dpi,
        background_color="white"
    )
    
    # Load as PIL Image
    img = Image.open(BytesIO(png_data))
    
    # Convert to RGB then to 1-bit
    img = img.convert("RGB")
    
    return img


def print_label_to_niimbot(address: str, svg_content: str, density: int = 3,
                           model: str = "b1", dpi: int = 203) -> bool:
    """
    High-level function to print an SVG label to a Niimbot printer.
    
    Args:
        address: Bluetooth address of the printer
        svg_content: SVG string content
        density: Print density 1-5
        model: Printer model (b1, b18, b21, d11, d110)
        dpi: Render DPI (203 for Niimbot B1)
    
    Returns:
        True on success
    """
    transport = NiimbotTransport(address)
    
    try:
        if not transport.connect():
            return False
        
        printer = NiimbotPrinter(transport, model)
        image = svg_to_image(svg_content, dpi)
        
        # Resize if needed for printhead
        max_width = NiimbotPrinter.MODEL_SPECS.get(model.lower(), 384)
        if image.width > max_width:
            ratio = max_width / image.width
            new_height = int(image.height * ratio)
            image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        printer.print_image(image, density=density)
        return True
        
    finally:
        transport.disconnect()

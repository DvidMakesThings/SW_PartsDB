# Transformer classification and properties

Added 2026-11-23 to `dmt_schema.json` and `dmt_templates.json`.

Family **07/06** previously had neither CC/SS guidelines nor a property template.
It now offers power, pulse/LAN/Ethernet, current-sense, SMPS/flyback, audio,
gate-drive and RF transformer classes, with mounting-style selections.
Existing classification definitions and part records are unchanged.

## Example: Würth Elektronik 749020111A

| Field | Selection / value |
|---|---|
| TT | 07 - Power Supplies and Magnetics |
| FF | 06 - Transformers |
| CC | 02 - Pulse / LAN / Ethernet transformers |
| SS | 01 - Surface mount (SMT / SMD) |
| MPN | 749020111A |
| Inductance | 350 µH min. |
| Turns Ratio - Primary:Secondary | 1:1 |
| Transformer Type | LAN 1000 Base-T |

The next sequence is assigned when the part is saved, yielding
`DMT-07060201XXX`. No inventory part or stock quantity is created by this
classification update.

The template includes the shared core fields: MPN, Location, Quantity, Value,
Manufacturer, Description, RoHS and Datasheet, plus mounting, package,
temperature and transformer-specific properties. TT/FF/CC/SS remain required
on the Add Part form. Unknown quantities can still be left blank; these JSON
field lists define available properties, not a new policy requiring every
electrical property or stock count to be known.

Values above describe this example part, not defaults for all transformers.
The manufacturer's datasheet specifies minimum inductance at 100 kHz/100 mV,
a 1:1 turns ratio (±5%), and 1000 Base-T operation:
[749020111A datasheet](https://www.we-online.com/components/products/datasheet/749020111A.pdf).

After restarting the application, open `/part/add` and select 07 then 06.
The same definitions are used by Edit Part, CSV import and the schema API.

# PartsDB Dark Theme UI

This is a dark theme UI implementation for PartsDB using React, Vite, TypeScript, TailwindCSS, and shadcn/ui components.

## Design Principles

- Dark theme with near-black background (#121212) and neutral-gray card surfaces (#1e1e1e)
- Cyan/blue highlights (#0ea5e9) for accent elements 
- Minimal spacing for information density
- Compact tables with small text
- Clean, professional look

## Folder Structure

- `/src/components/ui`: Contains shadcn/ui components with custom styling
- `/src/components/layout`: Contains layout components like Navbar
- `/src/lib/utils.ts`: Utility functions for UI components

## Getting Started

1. Install dependencies:

```bash
npm install
```

2. Start the development server:

```bash
npm run dev
```

## UI Components 

### Core Components

- `Button`: Buttons with various styles (primary, outline, destructive, ghost)
- `Input`: Form input fields
- `Select`: Dropdown selects with styling
- `Card`: Card containers with header, content, footer sections
- `Table`: Styled tables for data display
- `Tabs`: Tab navigation for component details
- `Pagination`: Page navigation for results

### Usage Example

```tsx
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Card, CardHeader, CardTitle, CardContent } from './components/ui/card';

function MyComponent() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>My Card Title</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <Input placeholder="Enter something..." />
          <Button>Submit</Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

## Theme Customization

The theme uses CSS variables defined in `src/index.css`:

```css
:root {
  --bg: #121212;
  --surface: #1e1e1e;
  --text: #e4e4e7;
  --border: #2e2e2e;
  --accent: #0ea5e9;
}
```

You can modify these values to customize the theme colors.
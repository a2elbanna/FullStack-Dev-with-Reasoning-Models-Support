This is the frontend portion of the fullstack template, built with Next.js, a React framework for production.

Project Structure

```
src/
├── app/                  # App Router (pages and layouts)
│   ├── page.tsx         # Home page
│   ├── layout.tsx       # Root layout
│   └── ...
├── components/          # Reusable UI components
│   ├── Header.tsx
│   ├── Hero.tsx
│   ├── Features.tsx
│   └── Footer.tsx
├── lib/                 # Utility functions
│   └── api.ts          # API client
└── app/globals.css      # Global styles
```

Styling

This project uses Tailwind CSS with the new `@import "tailwindcss"` syntax in `src/app/globals.css`. 
Tailwind configuration can be found in `tailwind.config.ts`. You can modify it 

Development Workflow

Creating New Pages:

1. Create a new directory in `src/app/` (e.g., `src/app/about/`)
2. Add a `page.tsx` file with your page content
3. Add a `layout.tsx` file if needed for specific layouts

Creating Components:

When building new features, you should generate components that follow these guidelines:

Component Structure:
- Each component should be in its own file in `src/components/`
- Use TypeScript with proper typing
- Export components as default exports
- Use PascalCase for component names

REQUIRED COMPONENTS:
1. Header.tsx - Navigation bar with links
2. Hero.tsx - Main landing section
3. Features/Services/Products sections - Based on the request
4. Footer.tsx - Footer with links and info
5. App.tsx - Main component that imports and arranges all components
6. src/index.css - With @tailwind directives

Component Design Principles:
- Use Tailwind CSS classes for styling
- Maintain consistent spacing and padding
- Implement responsive design with mobile-first approach
- Add proper hover states and transitions

API Integration

API calls are handled through the `src/lib/api.ts` file which uses Axios.

Environment Variables

Defined in a `.env.local` file in the root of the frontend directory.
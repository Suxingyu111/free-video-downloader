# UI Design System

## Required Design Skills

UI work must use:

- `ui-ux-pro-max` for design system, accessibility, touch target, contrast, and responsive review.
- `frontend-design` for distinctive visual direction and polished implementation.

## Visual Direction

Name: Industrial Media Console.

The product should feel like a serious media operations console: dark graphite surfaces, warm action colors, precise typography, compact panels, and clear status indicators.

## Avoided Styles

- Blue/purple AI gradients.
- Glassmorphism glow blobs.
- Generic AI SaaS hero pages.
- Emoji as structural icons.
- Low-contrast gray-on-dark UI.

## Color Tokens

```css
--color-bg: #0b0d0e;
--color-surface: #15191b;
--color-elevated: #1e2426;
--color-line: rgba(245, 243, 234, 0.10);
--color-text: #f5f3ea;
--color-muted: #9ca3a0;
--color-accent: #f59e0b;
--color-accent-strong: #f97316;
--color-success: #84cc16;
--color-danger: #ef4444;
```

## Typography

- Display and labels: JetBrains Mono or Fira Code.
- Body: Fira Sans or a similarly readable sans-serif.
- Body text must stay at 16px or above on mobile.

## Component Rules

- Primary buttons are at least 44px tall.
- Form fields have visible labels and helper/error text.
- State is never conveyed by color alone.
- Every icon-only button needs an accessible label.
- Animations use transform/opacity and respect reduced motion.
- Layout must work at 375px, 768px, 1024px, and 1440px.


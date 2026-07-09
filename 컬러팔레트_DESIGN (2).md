---
name: Gachibom Jeju Design System
colors:
  surface: '#f8f9fa'
  surface-dim: '#d9dadb'
  surface-bright: '#f8f9fa'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f5'
  surface-container: '#edeeef'
  surface-container-high: '#e7e8e9'
  surface-container-highest: '#e1e3e4'
  on-surface: '#191c1d'
  on-surface-variant: '#434656'
  inverse-surface: '#2e3132'
  inverse-on-surface: '#f0f1f2'
  outline: '#737688'
  outline-variant: '#c3c5d9'
  surface-tint: '#004ced'
  primary: '#003ec7'
  on-primary: '#ffffff'
  primary-container: '#0052ff'
  on-primary-container: '#dfe3ff'
  inverse-primary: '#b7c4ff'
  secondary: '#705d00'
  on-secondary: '#ffffff'
  secondary-container: '#fdd400'
  on-secondary-container: '#6f5c00'
  tertiary: '#454f5e'
  on-tertiary: '#ffffff'
  tertiary-container: '#5d6777'
  on-tertiary-container: '#dce6f9'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dde1ff'
  primary-fixed-dim: '#b7c4ff'
  on-primary-fixed: '#001452'
  on-primary-fixed-variant: '#0038b6'
  secondary-fixed: '#ffe170'
  secondary-fixed-dim: '#e9c400'
  on-secondary-fixed: '#221b00'
  on-secondary-fixed-variant: '#544600'
  tertiary-fixed: '#d9e3f6'
  tertiary-fixed-dim: '#bdc7d9'
  on-tertiary-fixed: '#121c2a'
  on-tertiary-fixed-variant: '#3d4756'
  background: '#f8f9fa'
  on-background: '#191c1d'
  surface-variant: '#e1e3e4'
typography:
  display-lg:
    fontFamily: JejuDoldam
    fontSize: 48px
    fontWeight: '400'
    lineHeight: '1.2'
  display-lg-mobile:
    fontFamily: JejuDoldam
    fontSize: 32px
    fontWeight: '400'
    lineHeight: '1.2'
  headline-md:
    fontFamily: JejuDoldam
    fontSize: 32px
    fontWeight: '400'
    lineHeight: '1.3'
  headline-md-mobile:
    fontFamily: JejuDoldam
    fontSize: 24px
    fontWeight: '400'
    lineHeight: '1.3'
  title-lg:
    fontFamily: Pretendard
    fontSize: 22px
    fontWeight: '700'
    lineHeight: 28px
  body-lg:
    fontFamily: Pretendard
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Pretendard
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Nanum Square
    fontSize: 14px
    fontWeight: '700'
    lineHeight: 20px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Nanum Square
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 48px
  xl: 80px
  gutter: 24px
  margin-mobile: 20px
  margin-desktop: 120px
---

## Brand & Style

The brand personality is **Professional, Reliable, and Empathetic**. It balances the rugged, natural beauty of Jeju Island with the high-tech precision of a modern travel concierge. The target audience includes travelers with mobility challenges, their families, and caregivers who require absolute certainty in accessibility data.

The design style is **Corporate Modern with Editorial Flair**. It utilizes heavy whitespace and a structured grid to create a "designer-portfolio" aesthetic that feels premium rather than clinical. High contrast is the foundational principle, ensuring that the interface is not only beautiful but serves as a benchmark for inclusive design.

## Colors

The palette is anchored by **Electric Blue**, evoking the deep ocean surrounding Jeju and signaling digital reliability. **Sun Yellow** acts as a high-visibility functional accent, specifically reserved for accessibility ratings and "A+" status indicators.

- **Primary (Electric Blue):** Used for primary actions, active states, and branding elements.
- **Secondary (Sun Yellow):** Used strictly for high-priority highlights and accessibility certification badges.
- **Neutral (Basalt Black):** Used for typography and deep structural borders to maintain high legibility.
- **Surface (Pure White/Surface-dim):** Pure white is the base for all content cards; Surface-dim is used for background grouping to create an editorial layered effect.

## Typography

The typographic hierarchy prioritizes local identity and maximum readability. 

- **JejuDoldam** is reserved for high-level display titles and place names. Its unique texture provides a sense of place. Due to its decorative nature, it should never be used for body text or labels.
- **Pretendard** is the workhorse font, optimized for high-legibility rendering across all devices. Large body sizes (18px) are preferred for general information to accommodate users with visual impairments.
- **Nanum Square** is utilized for navigation menus and utility labels, providing a clean, geometric contrast to the body text.

## Layout & Spacing

This design system uses a **Fluid Grid with Editorial Constraints**. 

- **Desktop:** 12-column grid with 120px side margins to create a focused, premium reading experience.
- **Mobile:** 4-column grid with 20px side margins. 
- **Rhythm:** A strict 8px spacing scale is used. Editorial layouts should lean towards `lg` (48px) and `xl` (80px) vertical padding between sections to allow the content to breathe and reduce cognitive load. 
- **Safe Areas:** Interactive elements must maintain a minimum 44px hit target area to ensure usability for users with limited motor control.

## Elevation & Depth

To maintain a clean, professional aesthetic, this design system avoids heavy shadows. Depth is communicated through:

- **Tonal Layering:** The primary background is `Pure White`, while secondary layout sections use `Surface-dim`. 
- **Low-Contrast Outlines:** Instead of shadows, cards and input fields use a 1px border of `Basalt Black` at 10% opacity.
- **Active Elevation:** Only the primary "Book Now" or "CTA" buttons use a soft, 15% opacity Electric Blue shadow to indicate interactivity.
- **Glassmorphism (Subtle):** Floating navigation bars use a backdrop blur (20px) with 90% white opacity to maintain context of the content underneath.

## Shapes

The shape language is **Rounded (8px)**. This radius is applied consistently to:
- Primary and secondary buttons.
- Content cards and imagery.
- Form inputs and dropdowns.

**Special Case:** Accessibility "A+" badges and status tags may use a **Pill-shape** (fully rounded) to distinguish them from interactive buttons.

## Components

- **Buttons:** Primary buttons are Solid Electric Blue with White text. Secondary buttons are Outlined Basalt Black. High-contrast hover states are required (darkening the blue by 10%).
- **Accessibility Chips:** Use Sun Yellow background with Basalt Black text. These must always be accompanied by a clear icon (e.g., wheelchair icon, ramp icon).
- **Cards:** White background, 8px radius, 1px subtle border. Images within cards should have a top-only 8px radius.
- **Inputs:** 16px font size minimum to prevent iOS zooming issues. Borders must darken to Electric Blue on focus.
- **Lists:** Use generous 16px vertical padding between list items. Every list item relating to a location must include a "distance" and "accessibility status" label.
- **Navigation:** Bottom-bar navigation on mobile for thumb-reachability, featuring high-contrast icons and Nanum Square labels.
---
theme: "Premium Engineering Dark"
version: "1.7.0"
tokens:
  colors:
    bg-base: "#0f1115"
    bg-surface: "#161920"
    bg-element: "#212631"
    bg-active: "#2b313e"
    accent: "#6366f1"
    text-main: "#f3f4f6"
    text-muted: "#9ca3af"
    border-subtle: "#242936"
    marker-inout: "#ef4444"
    marker-select: "#3b82f6"
    marker-final: "#10b981"
  geometry:
    radius-md: "8px"
    radius-lg: "12px"
  spacing:
    layout-padding: "24px"
    element-gap: "12px"
    sidebar-expanded: "220px"
    sidebar-contracted: "64px"
---

# Parcel Video Engine Architecture & UI Overhaul Specification

## 1. Left Sidebar Navigation & Dynamic Hitbox Collapse
* **Ghost Box Elimination Fix**: When switching from Expanded Mode (`220px`) to Contracted Mode (`64px`), ensure the selection background container (`bg-active`) and active tab focus elements strip out text strings and collapse instantly. The button click radius must conform exactly to `64px` wide with centered icon structures to avoid rendering stray block outlines or floating layout artifacts.
* **Modern Control Button Switch**: Replace any hardcoded text or square border elements on your sidebar control with a clean, absolute-positioned, round chevron controller button toggling between `lucide-chevron-left` and `lucide-chevron-right`. It must bleed over the sidebar divider with zero background bounding shadows.

## 2. Dynamic Media Engine Watch Folder Data Pipeline
* **Background Directory Tracking Loop**: Ensure the "Recent Videos" dashboard module pulls its file targets dynamically from your indexed setting directories array. If folders contain nested items, crawl the structures, sorting results on your UI by file modification timestamp logs.

## 3. Two-Column Locked Split Layout Matrix (Parcel View)
* **Responsive Control Alignment**: Enforce a strict horizontal grid wrapper. Video previews take up `65%` left-side width, config text fields lock to a vertical `35%` scroll block on the right. Never let loading operations flatten rows into squished ribbons.
* **Padding Constraints**: The main interactive layout space must maintain a strict padding boundary of `layout-padding` (`24px`) away from the left navigation boundary line.

## 4. Settings View & Layout Optimization
* **Eradicate Unnecessary Gaps**: Delete all structural dummy divs or blank filler spacer blocks inside the Settings component view. Your paths text rows and configuration panels must flow one right after another down the page using clean, unified padding blocks.

## 5. Shadow-Free Flat Elements
* **Flat Selection Modifiers**: Explicitly drop all `box-shadow` styles from dropdown elements, list layers, context pickers, and tooltips. Use a flat color border profile configured to your `border-subtle` design system parameter (`1px solid #242936`).

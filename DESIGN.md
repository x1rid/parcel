---
theme: "Premium Engineering Dark"
version: "1.6.0"
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
    marker-inout: "#ef4444"    # Red segment edges
    marker-select: "#3b82f6"   # Translucent Blue range selection
    marker-final: "#10b981"    # Green final track cut
  geometry:
    radius-md: "8px"
    radius-lg: "12px"
  spacing:
    layout-padding: "24px"
    element-gap: "12px"
    sidebar-expanded: "220px"
    sidebar-contracted: "64px"
---

# Video Engine Architecture & UI Overhaul Specification

## 1. Left Sidebar Navigation (Expandable / Tight Spacing Fix)
* **Collapse Logic Mechanics**: The navigation panel shifts between `sidebar-expanded` (`220px`) and `sidebar-contracted` (`64px`). The toggle switch must be a modern, flush button using a monochromatic Lucide chevron icon, discarding any legacy box borders.
* **Main Content Margins & Gaps**: The main container block to the right of the sidebar must have a strict left padding offset of `layout-padding` (`24px`). Never let main content layouts or settings options smash directly against the sidebar edge.

## 2. Watch Folders Backend Data Pipeline (Recent Videos Fix)
* **Active Scanning Lifecycle**: The dashboard's "Recent Videos" grid must actively run a backend system check across all absolute directory paths saved in the "Watch Folders" list inside Settings. 
* **Automatic Hydration**: When the app initializes, it must index files within these active watch directories, sort them by system modification date, and dynamically populate the Home dashboard grid.

## 3. Compressor Tab View Split-Pane Fix (Reference: image_e9b661.png)
* **Fixed Two-Column Matrix Layout**: When a video asset loads into the Compressor view, the interface must remain locked in a strict two-column layout grid. It must never collapse vertically or break input field rows into flat squished slices.
  * **Left Workspace Column (65% width)**: Houses the loaded video player canvas, media playback engine, and integrated timeline tracks.
  * **Right Configuration Column (35% width)**: A vertically scrollable, dedicated container for target parameters (Target size, Format, Encoder, Codec). Input fields must maintain full internal height and clear label visibility.
* **Player Default Fallback**: If no video file is actively selected, display an empty file-drop state card matching the surface background instead of hiding structural frames.

## 4. Media Editor Axis Alignment & Chromatic Timeline Tracking
* **Horizontal Center Alignment**: Group the timeline slice modifiers, clear items, and contextual keyframe elements into a unified horizontal layout block positioned precisely in the **center horizontal axis** beneath the media preview window.
* **Vector Brackets Only**: Remove all literal text string names on the segment cutting elements ("Mark In", "Mark Out"). Replace them with clean monochromatic vector line symbols.
* **Visual Range Indicators**: Draw colored state indicators over the editing asset timeline track components:
  * **In/Out Point Coordinates**: Vertical timeline handles styled in `marker-inout` (Vibrant Red).
  * **Highlighted Current Range**: A translucent block mask overlay using `marker-select` (Blue).
  * **Confirmed Cut Export Range**: Highlight the finalized export track segment block in `marker-final` (Vibrant Green).

## 5. Settings Panel Cleanliness & Component Shadows (Reference: image_e9b6c3.png)
* **Eradicate Black Box Artifacts**: Clean up the Watch Folders sub-section container. Remove all nested empty div blocks or unmapped layout placeholders causing random dark patches on the surface.
* **Flat Dropdown Elements**: Eliminate all drop shadows from context overlay boxes, input selection fields, and dropdown popup blocks. Replace blurry dark shadows with a sharp, high-visibility solid container border outline using the `border-subtle` token.
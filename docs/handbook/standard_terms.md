# Standard Terms (UI Labels)

This document defines the user-facing terminology for PhysicsLab. It does **not** change internal IDs, schemas, or folder names.

## Curriculum (content hierarchy)
- **Topic** = Module
- **Unit** = Section
- **Lesson** = Package
- **Activity** = Part

These labels describe curriculum structure and are what users see in the Content Browser and Content Management screens.

## Runtime (component system)
- **Pack** = Component Pack (installable runtime bundle)
- **Block** = Component (runtime component instance)

Packs/Blocks are runtime building blocks that can be used inside any Project.

## Project model
- **Project** = Workspace (the active sandbox and its prefs/runs)

Projects are the unit of work in the app. The active Project controls run storage, prefs, and pack enablement.

## Governance contract
- The **Management Core** (core_center) is the authority for inventory, jobs, runs, and projects.
- The UI surfaces this data and does not rename or rewrite internal IDs.

## Reserved wording
- “Package” is reserved for curriculum **Lesson** only.
- Installable runtime bundles are called **Packs**.

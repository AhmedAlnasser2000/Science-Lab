# PhysicsLab Glossary

## CodeSee Concepts

### Atlas
- **Meaning (plain English):** Graph view of components and relationships.
- **Real-life analogy:** City map showing places and roads between them.
- **In PhysicsLab:** Core visual map used by CodeSee.
- **Example:** Open CodeSee to inspect how packs and systems connect.
- **Common confusion (what it's NOT):** Not only a static picture; it reflects runtime-linked context.

### Badge
- **Meaning (plain English):** Compact status indicator.
- **Real-life analogy:** Tiny notification dot on a mobile app icon.
- **In PhysicsLab:** Small symbol/count shown on a node in CodeSee.
- **Example:** A node shows a badge when pulses, spans, or checks are active.
- **Common confusion (what it's NOT):** Not the full detail panel; use inspector/diagnostics for full context.

### Diff Mode
- **Meaning (plain English):** Compare two states.
- **Real-life analogy:** "Track changes" view between two document versions.
- **In PhysicsLab:** Snapshot comparison mode for node/edge changes.
- **Example:** Compare current graph with a saved snapshot to see added/removed nodes.
- **Common confusion (what it's NOT):** Not a live replay timeline.

### Lens
- **Meaning (plain English):** Predefined filtering/view mode.
- **Real-life analogy:** Camera mode presets (portrait, night, panorama).
- **In PhysicsLab:** Atlas, Platform, Content, Bus, Extensibility lenses.
- **Example:** Switch to Bus lens to focus on message flow entities.
- **Common confusion (what it's NOT):** Not a single-node detail popup.

### Dependents
- **Meaning (plain English):** Items that rely on the current item.
- **Real-life analogy:** Apps that stop working if one shared library is removed.
- **In PhysicsLab:** Incoming dependency relations shown in CodeSee Inspector.
- **Example:** In Relations, "Used by / Dependents" lists nodes that point to this node.
- **Common confusion (what it's NOT):** Not containment children; it is dependency direction.

### Paged list
- **Meaning (plain English):** List loaded in chunks rather than all at once.
- **Real-life analogy:** Reading search results page by page instead of opening all results.
- **In PhysicsLab:** Inspector Relations sections load 50 rows at a time with "Load more".
- **Example:** Large module relations show first page, then append more on demand.
- **Common confusion (what it's NOT):** Not a collapsed tree; it is progressive loading.

### Pulse
- **Meaning (plain English):** Animated activity signal.
- **Real-life analogy:** A heartbeat monitor spike indicating fresh activity.
- **In PhysicsLab:** Edge-following event pulse in the CodeSee graph.
- **Example:** A pulse animates across an edge after an event is emitted.
- **Common confusion (what it's NOT):** Not persistent state; pulses are transient activity hints.

### Snapshot
- **Meaning (plain English):** Saved point-in-time view.
- **Real-life analogy:** A photo taken at a specific moment.
- **In PhysicsLab:** Stored graph state used for review and diff.
- **Example:** Save snapshot before a change, then compare in Diff Mode.
- **Common confusion (what it's NOT):** Not an ongoing recording stream.

### Trail Mode
- **Meaning (plain English):** Lightweight path hint mode.
- **Real-life analogy:** Faint footprints showing where someone passed.
- **In PhysicsLab:** Shows touched areas without full sequence detail.
- **Example:** After quick interaction, trail hints remain without full trace details.
- **Common confusion (what it's NOT):** Not full causality reconstruction.

## Runtime and Messaging

### Bus
- **Meaning (plain English):** Message transport channel.
- **Real-life analogy:** A postal network that routes letters to the right addresses.
- **In PhysicsLab:** `runtime_bus` routes events and commands.
- **Example:** UI sends a request and receives a status reply through bus topics.
- **Common confusion (what it's NOT):** Not a direct function call stack.

### Span
- **Meaning (plain English):** Traced operation interval.
- **Real-life analogy:** Stopwatch timing for one specific task.
- **In PhysicsLab:** Used for runtime activity overlays and diagnostics.
- **Example:** A span starts when an action begins and ends when processing completes.
- **Common confusion (what it's NOT):** Not the same as a single log line.

### Topic
- **Meaning (plain English):** Named stream of messages.
- **Real-life analogy:** A radio frequency that listeners tune into.
- **In PhysicsLab:** Event channels consumed by UI and systems.
- **Example:** Inventory updates are published on a specific topic watched by screens.
- **Common confusion (what it's NOT):** Not global shared state by itself.

## Storage and Layout

### Repo vs Store
- **Meaning (plain English):** Source vs installed/runtime copy.
- **Real-life analogy:** Warehouse master inventory vs shelf-ready items in a store.
- **In PhysicsLab:** `*_repo` is source content, `*_store` is active copied state.
- **Example:** Packs are authored in repo then materialized into store for runtime use.
- **Common confusion (what it's NOT):** Not two separate product types; it is lifecycle stage.

### Layout State
- **Meaning (plain English):** Persisted panel positions/sizes.
- **Real-life analogy:** Saving your desk setup so it reopens the same way tomorrow.
- **In PhysicsLab:** Restores CodeSee dock/floating panel layout.
- **Example:** Lens palette reopens docked where you left it.
- **Common confusion (what it's NOT):** Not content data; only UI placement/settings.

### Registry
- **Meaning (plain English):** Indexed metadata for discoverability.
- **Real-life analogy:** A library catalog that points to books and their categories.
- **In PhysicsLab:** Tracks packs/plugins/components for quick lookup.
- **Example:** Discovery screens read registry entries to populate install/manage lists.
- **Common confusion (what it's NOT):** Not the full payload storage for every item.

## Workspaces and Runs

### Workspace
- **Meaning (plain English):** Isolated project environment.
- **Real-life analogy:** A dedicated project room with its own materials and notes.
- **In PhysicsLab:** Holds selected packs, content, and run history.
- **Example:** Switching workspace changes active content and configuration scope.
- **Common confusion (what it's NOT):** Not only a UI profile; it includes runtime context.

### Run
- **Meaning (plain English):** A concrete execution/iteration.
- **Real-life analogy:** One lab experiment attempt with recorded observations.
- **In PhysicsLab:** Timestamped activity session with logs/status.
- **Example:** A run records what happened during one simulation/test cycle.
- **Common confusion (what it's NOT):** Not equivalent to a workspace.

### Template
- **Meaning (plain English):** Starting blueprint.
- **Real-life analogy:** A pre-filled form you copy before starting a new case.
- **In PhysicsLab:** Base setup used to create new workspaces quickly.
- **Example:** Create a workspace from a template to pre-load packs and defaults.
- **Common confusion (what it's NOT):** Not immutable; workspaces created from it can diverge.

# Runtime Bus: Trace, Trail, and Messages

## Event
- **Meaning (plain English):** Something that happened.
- **Real-life analogy:** A timestamped log line in a delivery center.
- **In PhysicsLab:** Runtime notification emitted on a bus topic.
- **Example:** "inventory.refresh.completed" event after refresh finishes.
- **Common confusion (what it's NOT):** Not always a command request.

## Trail mode
- **Meaning (plain English):** Lightweight activity hints.
- **Real-life analogy:** Footprints in sand showing that movement occurred.
- **In PhysicsLab:** Shows touched zones without full timeline details.
- **Example:** A node gets a trail badge after quick interaction.
- **Common confusion (what it's NOT):** Not full causality reconstruction.

## Trace mode
- **Meaning (plain English):** Detailed operation timeline.
- **Real-life analogy:** Parcel tracking with each handoff step.
- **In PhysicsLab:** Correlated sequence of spans/events with context.
- **Example:** Follow a request from UI trigger to runtime completion.
- **Common confusion (what it's NOT):** Not only error logs.

## Request/Reply
- **Meaning (plain English):** Ask for data and wait for response.
- **Real-life analogy:** Ticket desk query and official answer.
- **In PhysicsLab:** Common pattern for inventory/status API calls.
- **Example:** UI asks runtime for current pack registry summary.
- **Common confusion (what it's NOT):** Not pub/sub broadcast mode.

## Pub/Sub
- **Meaning (plain English):** Broadcast updates to any subscribers.
- **Real-life analogy:** Radio station and listeners.
- **In PhysicsLab:** Bus topics distribute events to multiple consumers.
- **Example:** Status updates pushed to both UI and diagnostics collectors.
- **Common confusion (what it's NOT):** Not one-to-one RPC.

# Karlz AI — AI Usage screen: use device-local timezone for reset labels

**Written:** 2026-07-12
**Backend commit:** `karlwireless/Token-Usage-` @ `7e54b34`
**Target app repo:** `karlwireless/Karlz_AI`
**Owner:** Karl (`karl@susmaninsurance.com`)

## Why

The `usage-api` on gort (`https://gort.pitta-crested.ts.net:7811/api/usage`)
used to pre-format reset times as strings in a hardcoded `America/Los_Angeles`
timezone. Fine when your phone is in PT, wrong the moment you or a tester
is anywhere else. Fixed on the backend as of `7e54b34` — the API now sends
raw epoch seconds alongside the pre-formatted strings. The app should read
the epoch and format for the device's local TZ.

## What changed on the API — additive only, nothing breaks

Every provider object in `/api/usage` now includes two new fields alongside
what was already there:

```jsonc
{
  "id": "claude",
  "pct": 49,
  "reset": "1:50 PM",        // ← existing: pre-formatted in America/Los_Angeles
  "resetAt": 1783889400,     // ← NEW: raw unix epoch seconds (or null)
  "weeklyPct": 4,
  "weeklyReset": "10:00 AM", // ← existing
  "weeklyResetAt": 1784410000, // ← NEW: raw unix epoch seconds (or null)
  "ok": true,
  "source": "gort-claude-api"
}
```

- `resetAt` / `weeklyResetAt` are **Int64 unix seconds** (or `null`).
- The old `reset` / `weeklyReset` strings **stay** for backwards compat.
- The app should **prefer `resetAt`** when non-null, fall back to `reset`
  when null.

### Per-provider notes

| id | `resetAt` present? | Notes |
|---|---|---|
| `claude` | ✓ | From Anthropic `anthropic-ratelimit-unified-*-reset` headers. |
| `codex` | ✓ | From OpenAI session `rate_limits.primary/secondary.resets_at`. |
| `zai` | ✓ | From z.ai monitor endpoint. |
| `ollama` | ✗ (always null) | Ollama's HTML gives us a relative string ("3 hours"), not a timestamp. Keep displaying `reset` as-is for this one — it's already TZ-agnostic. |

## What to change in the iOS + watch app

### 1. Model — add the two new fields to `UsageProvider`

Assumed file: `Shared/UsageShared.swift` (holds `UsageProvider` / `UsageSnapshot`).

```swift
struct UsageProvider: Codable, Identifiable {
    let id: String
    let name: String
    let label: String?
    let pct: Double?
    let reset: String            // existing pre-formatted string, keep as fallback
    let resetAt: Int64?          // NEW — unix seconds, may be nil
    let weeklyPct: Double?
    let weeklyReset: String
    let weeklyResetAt: Int64?    // NEW — unix seconds, may be nil
    let ok: Bool
    let source: String?
    let extra: String?
    // ... whatever else the struct already has (stale, ageSec, etc.)
}
```

Since the fields are optional, existing decoding of older cached snapshots
keeps working. No migration needed.

### 2. Formatter — one small helper to prefer epoch, fall back to string

Assumed file: `Shared/UsageShared.swift` (`UsageFormat` helper).

```swift
extension UsageFormat {
    /// Format a provider's reset in the device's local timezone.
    /// Prefers `resetAt` epoch when available, falls back to the
    /// pre-formatted string the API also ships.
    static func resetLabel(epoch: Int64?, fallback: String) -> String {
        guard let epoch = epoch, epoch > 0 else { return fallback }
        let date = Date(timeIntervalSince1970: TimeInterval(epoch))
        let f = DateFormatter()
        f.timeZone = TimeZone.current          // ← device-local
        f.locale = Locale.current
        f.dateStyle = .none
        f.timeStyle = .short                   // e.g. "1:50 PM"
        // Optional: if the reset is more than ~24h out, include a short date
        if date.timeIntervalSinceNow > 24 * 3600 {
            f.dateStyle = .short               // e.g. "7/19, 12:40 PM"
        }
        return f.string(from: date)
    }
}
```

### 3. View — call the new formatter

Assumed files: `OpenClawCompanion/Usage/UsageView.swift` and
`KarlzAIWatch/WatchUsageView.swift`.

Wherever the view currently reads `provider.reset` / `provider.weeklyReset`,
replace with:

```swift
// iOS or watch — anywhere you display the reset label
let shortReset = UsageFormat.resetLabel(
    epoch: provider.resetAt,
    fallback: provider.reset
)

let weeklyReset = UsageFormat.resetLabel(
    epoch: provider.weeklyResetAt,
    fallback: provider.weeklyReset
)
```

Ollama's `resetAt` will always be `nil`, so it falls back to the API's
pre-formatted string, which is already relative ("3 hours") and
timezone-agnostic — no change in behavior for that tile.

## Testing

1. **Simulator, US-Pacific:** matches the current label exactly (no change).
2. **Simulator, US-Eastern:** the Codex 5h label should show 3 hours later
   than the Pacific label. e.g. `"12:40 PM"` on PT sim → `"3:40 PM"` on ET sim.
3. **Simulator, Europe/London:** Codex label should show 7–8 hours later
   than PT sim.
4. **Ollama tile in any TZ:** unchanged (still shows "3 hours" or whatever
   the API relative string is).
5. **When resetAt is missing** (should never happen for claude/codex/zai
   once the backend deploys, but Ollama is always null): app must fall
   back cleanly to `reset` without crashing.

Change the device TZ in **Settings → General → Date & Time → Time Zone**
(disable "Set Automatically" first) to test different regions.

## Backwards compatibility notes

- **API stays fully backwards compatible.** Old app builds that only know
  `reset` / `weeklyReset` keep working unchanged; the new fields are just
  ignored by them.
- **Cached snapshots** from prior versions decode fine because the new
  fields are optional.
- **No app-store rollout coordination needed** — you can ship the app
  change whenever; the backend already supports both callers.

## Reference — where to see the raw fields

To eyeball the new fields on the deployed backend:

```sh
curl -sk https://gort.pitta-crested.ts.net:7811/api/usage \
  | python3 -m json.tool
```

Sample response element (as of writing):

```json
{
  "id": "codex",
  "pct": 0,
  "reset": "12:40 PM",
  "resetAt": 1784490036,
  "weeklyPct": null,
  "weeklyReset": "",
  "weeklyResetAt": null,
  "ok": true,
  "label": "Pro",
  "source": "coder-codex-sessions"
}
```

Any questions ping Karl.

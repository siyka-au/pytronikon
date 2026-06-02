# Elektronikon mkv.cgi protocol notes

## Summary

The embedded web UI is a legacy JavaScript client that polls `POST /cgi-bin/mkv.cgi`
every 5 seconds. The request body is a single form field:

```text
QUESTION=<selector><selector><selector>...
```

Each selector is 6 hex characters:

- 4 hex characters: object index
- 2 hex characters: subindex

Example: `300301` means index `0x3003`, subindex `0x01`.

The response is a packed string aligned to those selectors:

- successful answer: 8 hex characters
- missing answer: single `X`

The client splits large batches into chunks of 1000 selectors before posting.

## Legacy client behavior

The browser forces synchronous jQuery AJAX during startup and polling. The flow is:

1. bootstrap metadata with `Q_2000_*`
2. build active point lists with label IDs, units, and runtime subindices
3. poll live values every 5 seconds with `Q_3000_*`
4. format labels and units in JavaScript, not on the device

Important implications for a replacement client:

- you do not need to mirror the bad synchronous browser behavior
- you do need a discovery phase before polling live values
- labels come from client-side language tables keyed by `MPL`
- some values are raw engineering data and need client-side scaling

## Current page capture

One captured request body from the shared browser page:

```text
300301 300302 300303
300701 300702 300703 300704 300705 300707
300501 300502 300503 300504 300505 300506
300e01 300e02 300e03 300e18
311301 311303 311304 311305 311307 311308 311309 31130a 31130b 31130c 31130d 31130e 31130f 311310 311311 311312 311313 311314 311315 311316 311317 311318 311319 31131a 31131b 31131c 31131d 31131e 31131f 311320 311321 311322 311323 311324 311325 311326 311327 311328 311329 31132a
311401 311402 311403 311404 311405 311406 311407 311408 311409 31140a 31140b 31140c 31140d 31140e 31140f 311410 311411 311412
300901
300108
```

Observed mapping:

- `0x3003`: digital inputs
- `0x3005`: digital outputs
- `0x3007`: counters
- `0x300E`: special protections
- `0x3113` and `0x3114`: ES controller data
- `0x3009`: service plan
- `0x3001`: machine state

## Decoding examples

Captured response alignment:

```text
300301 -> 00010080
300302 -> 00010080
300303 -> 00000080
300701 -> 08E15998
300702 -> 021B37CE
300703 -> 00022436
300704 -> 0045EDB4
300705 -> 0000101B
300707 -> 14320455
300501 -> 00010080
300502 -> 00000080
300503 -> 00010080
300504 -> 00000080
300505 -> 00010080
300506 -> 00010080
300e01 -> 23000000
300e02 -> 23010000
300e03 -> 23020000
300e18 -> 23170000
311301 -> 00000000
311303..311412 -> X
300901 -> 00000000
300108 -> 00000012
```

Examples that match the visible UI:

- `300301 -> 00010080`: digital input 1 value is `1`, which matches `Closed`
- `300303 -> 00000080`: digital input 3 value is `0`, which matches `Open`
- `300703 -> 00022436`: counter value `0x22436 = 140342`, matching `Motor Starts`
- `300704 -> 0045EDB4`: counter value `0x45EDB4 = 4582836`, matching `Load Relay`
- `300701 -> 08E15998`: raw value `148986264` seconds, which the UI displays as `41385 hrs`
- `300702 -> 021B37CE`: raw value `35338190` seconds, which the UI displays as `9816 hrs`
- `300707 -> 14320455`: raw value `338822229` seconds, which the UI displays as `94117 hrs`

So at least some counters are stored in seconds and converted to hours in the client.

## Data helpers used by the browser client

The browser-side decoder effectively uses these rules:

- `UInt32(data)`: parse all 8 hex characters as one big-endian unsigned integer
- `UInt16(word=1)`: first 4 hex characters
- `UInt16(word=0)`: last 4 hex characters
- `Byte(byte=1)`: bytes 3..4 of the 8-char payload according to the legacy helper
- `Byte(byte=0)`: bytes 1..2 of the 8-char payload according to the legacy helper

The page then formats values locally:

- labels via `MPL` lookup in the language file
- machine states via language tables
- counter units and time conversion in client-side formatting functions

## Reverse-engineered page model

The page does not hard-code the active point list. It discovers it by scanning metadata ranges:

- digital inputs: metadata range `0x20B0..0x20FF`, live values at `0x3003`
- digital outputs: metadata range `0x2100..0x214F`, live values at `0x3005`
- counters: metadata range `0x2607`, subindex `1..255`, live values at `0x3007`
- special protections: metadata range `0x2300..0x247E`, live values at `0x300E`
- machine state: metadata `0x2601/1`, live values at `0x3001/8` and sometimes `/9`
- internal data: metadata `0x2619`, live values at `0x3014`
- service plan: metadata `0x2602`, live values at `0x3009`
- ES data: live values at `0x3113` and `0x3114`

## Recommended replacement architecture

For a Node-RED friendly client, keep the protocol split into two stages:

1. Discovery
   - fetch metadata ranges once at startup
   - build a point catalog with group, index, subindex, `RTD_SI`, `MPL`, and unit/type info

2. Polling
   - generate only the live selectors needed for the active points
   - send one `QUESTION=` batch
   - decode payloads into typed values
   - expose both raw values and normalized values

Recommended output shape for each point:

```json
{
  "group": "digital-input",
  "index": "0x3003",
  "subindex": 1,
  "rtdSi": 1,
  "mpl": 1234,
  "quality": 128,
  "raw": "00010080",
  "value": 1,
  "display": "Closed"
}
```

Recommended implementation choices:

- use async HTTP, not synchronous browser-style calls
- keep a request builder that can batch and split at 1000 selectors
- preserve raw payloads for later reverse-engineering
- cache the language file separately from telemetry polling
- treat `X` as unavailable data, not as zero
- keep formatting separate from transport and decoding

## Next practical step

Build a small Node or Node-RED module with three layers:

1. transport: `QUESTION` batch post and response alignment
2. codec: `UInt32`, `UInt16`, `Byte`, and group-specific decoders
3. catalog: metadata discovery and label resolution

That gets you a usable client without reproducing the brittle browser UI.

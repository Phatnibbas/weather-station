# ESP32 ThingSpeak HTTPS/TLS Postmortem — 2026-07-22

## Final operating state

**Status:** rolled back after hardware experiments.

The ESP32 is running the checked-in legacy firmware, not an experimental TLS build. The following three files were read back or hashed after rollback and matched:

| Artifact | SHA-256 |
|---|---|
| Local `firmware/siuuuu.py` | `b783ed14fa623c33b9e8435253c6dd6c82f7db35976fbed152081fd771d4c5bb` |
| Board `/main.py` | `b783ed14fa623c33b9e8435253c6dd6c82f7db35976fbed152081fd771d4c5bb` |
| Board `/main_legacy.py` | `b783ed14fa623c33b9e8435253c6dd6c82f7db35976fbed152081fd771d4c5bb` |

Runtime identity observed on the board:

- MicroPython `v1.26.1` (`ESP32_GENERIC`)
- ESP-IDF `v5.4.2`
- `requests` is a frozen module reported as `requests/__init__.py`
- USB serial: CH340, observed as `COM25` in this session; the COM number is not a permanent identity

The deployed legacy firmware still may stop at `Sending data to ThingSpeak...`. Phát explicitly accepted this rollback for now and will power-cycle/reload the station when necessary. Do not describe the HTTPS hang as fixed.

## What the board proved

### Reproduction

The full firmware repeatedly completed LCD, Wi-Fi, and all four Modbus reads, then stopped after:

```text
Sending data to ThingSpeak...
HTTP POST start (timeout=15 s)
```

Adding `timeout=15` to the frozen `requests.post()` call did not make the call return after 15 seconds. A socket timeout argument is therefore not a demonstrated hard deadline for this board's blocking TLS path.

### Stage localization

Instrumenting a raw HTTPS implementation localized the block:

```text
HTTP DNS done
HTTP TCP connect done
HTTP TLS wrap start
```

The next line, `HTTP TLS wrap done`, never appeared. A 45-second hardware watchdog then reset the board and reported `BOOT-WDT`. This isolates the observed hard block to synchronous `tls.SSLContext.wrap_socket()` in the full firmware state, after DNS and TCP connection.

### Minimal probes that passed

The same board and network completed all of the following in isolated probes:

- DNS lookup
- TCP connect to `api.thingspeak.com:443`
- synchronous TLS wrap
- HTTPS write/read
- raw POST with the real payload/key, returning HTTP 200 and ThingSpeak entry IDs `24584` and `24585`
- deferred nonblocking TLS probe, returning `HTTP/1.1 400 Bad Request` with a deliberately invalid API key

The `400` response in the last probe was expected; it proves the transport completed without creating a valid update.

Therefore, the endpoint, DNS, TCP, TLS stack, key, and payload are not globally broken. The failure depends on the resource/runtime state of the full firmware.

### Full-firmware nonblocking experiment that failed

Deferred nonblocking TLS avoided the original blocking `wrap_socket()` call, but in the full firmware it failed during RSA handshake with:

```text
MBEDTLS_ERR_RSA_PUBLIC_FAILED + MBEDTLS_ERR_MPI_ALLOC_FAILED
```

The error repeated on successive upload attempts. This is evidence consistent with an allocation/resource failure during the full-firmware mbedTLS handshake; the exact ESP-IDF/mbedTLS heap cause remains unverified because no `esp32.idf_heap_info()` measurements were captured. It is not evidence that Python `gc.mem_free()` alone measures or controls the relevant heap.

The experiment was rejected and the board was rolled back from `/main_legacy.py`.

## Approaches rejected by runtime evidence

| Approach | Hardware result | Decision |
|---|---|---|
| Add `timeout=15` to `requests.post()` | Still blocked beyond 15 s | Rejected as a hard deadline |
| `gc.collect()` immediately before frozen `requests.post()` | Minimal probe passed; full firmware still blocked | Insufficient |
| Raw synchronous socket + TLS | Minimal probe passed; full firmware blocked in `wrap_socket()` | Rejected |
| 45-second WDT around blocking TLS | Reset/recovered, then entered repeated `BOOT-WDT` loop | Recovery boundary works, but not a usable uploader |
| Deferred nonblocking TLS + `poll()` | Probe passed; full firmware raised mbedTLS MPI allocation failure | Rejected for this firmware/runtime state |
| Host mocks/stubs | Passed request/control-flow tests | Never accepted as ESP32 TLS evidence |

## Rules for the next agent

1. **Read this postmortem before changing station networking.**
2. **Do not claim that `timeout=` bounds TLS on this board.** The board disproved that claim.
3. **Do not infer full-firmware viability from a minimal TLS probe.** The probe had approximately 110 KiB of MicroPython GC heap free but did not reproduce the full firmware's mbedTLS/ESP-IDF heap state.
4. **Treat Python GC heap and mbedTLS/ESP-IDF heap as different evidence domains.** `gc.collect()` is not proof that RSA handshake memory is available.
5. **Preserve rollback before every hardware experiment:** copy `/main.py` to `/main_legacy.py`, hash both, and define the rollback command before overwriting `/main.py`.
6. **Use `mpremote` directly when available.** Thonny is not required for upload; both use the serial REPL. Close Thonny first because it holds the COM port.
7. **A copied file/hash proves deployment only.** Runtime success requires serial evidence through the HTTP response/body and, ideally, multiple upload cycles.
8. **Do not revive the deleted host resilience suite as final proof.** It was written against experimental firmware branches and became stale after rollback.
9. **Do not silently change to plaintext HTTP.** Any security downgrade requires an explicit decision.
10. **Stop after three failed architecture attempts.** The next credible work is a separate resource-reduction/firmware-runtime investigation, not another timeout wrapper.

## Credible next investigation, if reopened

This incident is closed for now. If it is reopened, first measure and reduce the full runtime's ESP-IDF/mbedTLS memory pressure before touching request semantics. Candidate work must be a new approved plan and may include:

- capture `gc.mem_free()` and `esp32.idf_heap_info()` before/after LCD, Wi-Fi, UART allocation, sensor reads, TLS context creation, and handshake;
- test whether disabling/deinitializing optional peripherals before upload changes IDF heap enough for RSA;
- compare a clean minimal firmware that incrementally adds station subsystems until the TLS failure appears;
- evaluate a MicroPython build/configuration with smaller TLS buffers or a different certificate/cipher path;
- move cloud upload to a separate gateway only if the architecture/product permits it.

Do not begin those experiments implicitly while performing unrelated application work.

## Deployment and rollback commands

Direct upload does not require Thonny:

```powershell
py -3 -m mpremote connect COM25 fs cp firmware/siuuuu.py :main.py
py -3 -m mpremote connect COM25 fs sha256sum :main.py
py -3 -m mpremote connect COM25 reset
```

Before an experiment:

```powershell
py -3 -m mpremote connect COM25 fs cp :main.py :main_legacy.py
py -3 -m mpremote connect COM25 fs sha256sum :main.py :main_legacy.py
```

Rollback:

```powershell
py -3 -m mpremote connect COM25 fs cp :main_legacy.py :main.py
py -3 -m mpremote connect COM25 fs sha256sum :main.py :main_legacy.py
py -3 -m mpremote connect COM25 reset
```

If the CH340 disappears from the current COM-port list, unplug/replug USB and rediscover the port; do not assume it remains `COM25`.

## Evidence classification

- **EVIDENCED:** serial logs and hash checks obtained from the physical ESP32 during this session.
- **USER-CONFIRMED:** Phát accepted the final rollback and the current operational compromise.
- **UNKNOWN:** whether a resource-reduced full firmware can complete TLS reliably over long unattended operation.
- **NOT ESTABLISHED:** root electrical cause of earlier station gaps, long-term stability, or a permanent HTTPS fix.

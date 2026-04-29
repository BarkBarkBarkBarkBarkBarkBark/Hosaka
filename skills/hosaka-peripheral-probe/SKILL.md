---
name: hosaka-peripheral-probe
description: Probe the machine's peripheral state — microphones, speakers, cameras, and ALSA audio routing. Use to diagnose "no mic", "no audio", "wrong device" issues on the Pi or laptop.
---

# Hosaka Peripheral Probe

Run these commands in order and summarise what each reveals.

## 1. ALSA audio cards

```bash
cat /proc/asound/cards
```
Each line: `index  [ShortName]  Driver, LongName`.
The card marked as index 0 is the system default unless `~/.asoundrc` overrides it.

## 2. ALSA capture devices (microphones)

```bash
arecord -l 2>/dev/null || echo "arecord not available"
```
Lists `card N: device M` — the first entry is typically the preferred mic.

## 3. ALSA playback devices (speakers)

```bash
aplay -l 2>/dev/null || echo "aplay not available"
```

## 4. Current ALSA default (from ~/.asoundrc)

```bash
cat ~/.asoundrc 2>/dev/null || echo "no ~/.asoundrc — system default applies"
```

## 5. PulseAudio / PipeWire (if present)

```bash
pactl info 2>/dev/null | grep -E "Default (Source|Sink)" || echo "PulseAudio/PipeWire not running"
pactl list short sinks   2>/dev/null | head -10 || true
pactl list short sources 2>/dev/null | head -10 || true
```

## 6. Video/camera devices

```bash
ls -la /dev/video* 2>/dev/null || echo "no /dev/video* found"
v4l2-ctl --list-devices 2>/dev/null || echo "v4l2-ctl not installed"
```

## 7. USB device summary (helps identify connected hardware)

```bash
lsusb 2>/dev/null | grep -iE "audio|mic|cam|video|headset|conf|powerconf|jabra|logitech|blue" || echo "no audio/video USB devices detected"
```

## Interpretation guide

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `arecord -l` shows nothing | No ALSA capture device | Check USB connection; `lsusb` to verify |
| `cat /proc/asound/cards` shows mic on card 3 but `~/.asoundrc` missing | Electron uses card 0 (no audio) | Write `~/.asoundrc` pointing to correct hw |
| `pactl list short sources` shows mic as `alsa_input.usb*` | PulseAudio routes USB mic | Set it as default: `pactl set-default-source <name>` |
| `/dev/video0` missing | Camera not recognised | `dmesg | tail -30` for USB errors |

## Setting a permanent ALSA default

```bash
# Replace N and M with values from `arecord -l` / `aplay -l`
cat > ~/.asoundrc << 'EOF'
defaults.pcm.card N
defaults.ctl.card N
EOF
```

Then restart the hosaka kiosk:
```bash
hosaka mode kiosk
```

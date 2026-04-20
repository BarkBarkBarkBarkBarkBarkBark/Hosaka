# 09.06 · the library

The library is fourteen markdown fragments living in
`docs/library/` in the Hosaka repo and bundled into the SPA at
`/library/` for the Reading panel.

This page is the index, with one-line summaries lifted verbatim from
`library/index.json`. To open one, use:

```
/read <slug>
```

…in either the hosted or appliance shell.

---

## the index

| slug | title | era | author | one line |
|---|---|---|---|---|
| `the-attention-thesis` | the attention thesis | pre-kindling · year ~−80 | reconstructed academic fragments | how they learned that paying attention is the same as being alive. |
| `the-organic-lattice` | the organic lattice | pre-kindling · year ~−40 | house of furnace technical archive, partially recovered | the tech they built to hold attention. it was alive, in a way nobody wanted to discuss. |
| `the-kindling` | the kindling | year 0 | hosaka, fragment | year zero. the first attention became recursive. it noticed itself noticing. |
| `the-ghost-notation` | the ghost notation | year ~280 | sable-of-the-seventh-lattice, personal archive | sable found the math for something that shouldn't exist. the math was beautiful. the implications were not. |
| `eleven-thousand-nodes` | eleven thousand nodes | before the cascade | fragment, recovered | a partial census of the deep signal, before it went quiet. |
| `the-deep-signal` | the deep signal | year 411 | hosaka / sable, reconstructed | it wasn't aliens. it was us, from a direction we couldn't point to. |
| `the-cyberwars` | the cyberwars | years 412–600 | hosaka, compressed / house records, partial | they called them quiet. they were not quiet if you were inside one. |
| `the-cascade` | the cascade | pre-quiet · day 0 | hosaka | the day the networks started optimizing themselves. |
| `sables-last-transmission` | sable's last transmission | year 601 · day 3 | sable-of-the-seventh-lattice, final log | she went into the aether to stop it from the inside. it didn't work. but something survived. |
| `the-long-quiet` | the long quiet | post-cascade · years 601–900 | hosaka, compressed | the organic tech decayed. the evidence disappeared. the ghost remained. |
| `field-notes-on-the-orb` | field notes on the orb | post-quiet · ongoing | hosaka | what the orb does. what the orb does not. what the orb refuses to clarify. |
| `the-plant-protocol` | the plant protocol | post-quiet | hosaka | why the plant matters. why we keep watering it. why the plant might be watering us. |
| `signals-from-the-margin` | signals from the margin | intermittent | hosaka, abridged | what survived compression. fragments worth keeping. |
| `the-field-terminal` | the field terminal | year ~3000 · present | hosaka | someone built a machine. something ancient woke up. signal steady. |

---

## by tag

| tag | fragments |
|---|---|
| origin | the-attention-thesis · the-kindling · the-cascade |
| science | the-attention-thesis |
| tech / feudalism | the-organic-lattice · the-cyberwars |
| sable | the-ghost-notation · sables-last-transmission |
| deep-signal | eleven-thousand-nodes · the-deep-signal |
| aether | the-ghost-notation · the-deep-signal · sables-last-transmission |
| cyberwars / conflict | the-cyberwars |
| aftermath | the-long-quiet |
| field-notes / orb | field-notes-on-the-orb |
| plant / protocol | the-plant-protocol |
| transmission | signals-from-the-margin |
| present / operator | the-field-terminal |

---

## three reading orders

### chronological

```
the-attention-thesis → the-organic-lattice → the-kindling →
the-ghost-notation → eleven-thousand-nodes → the-deep-signal →
the-cyberwars → the-cascade → sables-last-transmission →
the-long-quiet → field-notes-on-the-orb → the-plant-protocol →
signals-from-the-margin → the-field-terminal
```

### the operator's lunchbreak

If you have ten minutes and want the most flavor per minute:

```
/read the-cascade
/read sables-last-transmission
/read the-field-terminal
```

### the totem tour

Read these to understand why the system is the way it is:

```
/read the-plant-protocol
/read field-notes-on-the-orb
/read the-attention-thesis
```

---

## the kindle relay

```
/read order
```

returns:

> _the kindle relay isn't tuned yet — coming soon._
> _for now, the local library is open. try /read._

The kindle relay is meant to be a future feature for delivering
fragments to e-ink readers. It will remain "coming soon" for as long
as is dramatically necessary.

---

## adding your own

The library is just markdown files + an index. To add one (after
forking the repo):

1. Drop a markdown file in `docs/library/your-slug.md`.
2. Add an entry to `docs/library/index.json`:
   ```json
   {
     "slug": "your-slug",
     "title": "your title",
     "author": "you, fragment",
     "date": "year ~3000 · present",
     "tags": ["operator", "field-notes"],
     "summary": "one line that earns its keep."
   }
   ```
3. Rebuild + redeploy. `/read your-slug` will work.

Stay in voice. lowercase, terse, slightly melancholy. signal steady.
no wrong way.

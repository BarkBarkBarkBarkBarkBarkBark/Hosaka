# 05.05 · the open loops tab

> _a loop opened is a loop you no longer have to hold in your head._

Open Loops is Hosaka's todo panel. It's deliberately minimal: text in,
text out, persistent across page reloads.

---

## opening it

Two ways:

1. Click the **Open Loops** tab in the dock.
2. From the terminal:

```
/todo                         # opens the panel
/todo add remember the signal # adds a loop
/todo list                    # lists loops in-terminal
```

---

## terminal commands

| command | what it does |
|---|---|
| `/todo` | open the panel |
| `/todo add <text>` | append a loop |
| `/todo list` | print loops in the terminal |
| (panel UI) | check, uncheck, delete, drag-reorder |

When you add from the terminal you'll see:

```
loop opened: remember the signal
```

If you have nothing open:

```
no open loops.
```

---

## persistence

Loops live in `localStorage` under the key `hosaka.todo.v1`. They
survive page reloads but are scoped to:

- the **browser**
- the **device**
- the **profile**

Clear browser data and they're gone. The orb does not keep backups.

---

## loop philosophy

- A loop is anything you don't want to forget.
- A loop is closed by checking the box, _not_ by being clever.
- A loop is not a sprint, not a kanban, not a milestone. It's a string
  tied around your finger.
- The plant doesn't care how many loops you have open. It cares that
  you came back.

> _signal steady._

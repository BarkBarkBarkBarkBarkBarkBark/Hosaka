/**
 * GamesPanel — lightweight arcade for the kiosk.
 *
 * Four pure-canvas games, no dependencies. Each game is an object with
 * `start(ctx, ctrl)` returning a `stop()` cleanup. Controls come from a
 * shared keyboard + on-screen-button bus so the same code works on the
 * 800×480 touchscreen and on a desk with a keyboard.
 *
 * Games:
 *   pong    — left paddle = w/s + on-screen ▲▼, AI on the right
 *   snake   — wasd / arrows / on-screen d-pad
 *   tetris  — left/right/down + rotate (z) + drop (space) + d-pad
 *   invaders— left/right + fire (space / button)
 */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";

type GameId =
  | "pong"
  | "snake"
  | "tetris"
  | "invaders"
  | "breakout"
  | "orb"
  | "lunar"
  | "signal";

type Ctrl = {
  // a control source emits "down"/"up" events keyed by an abstract action.
  on: (cb: (action: Action, kind: "down" | "up") => void) => () => void;
  pressed: (action: Action) => boolean;
};

type Action = "left" | "right" | "up" | "down" | "fire" | "rotate";

type Game = {
  start: (ctx: CanvasRenderingContext2D, ctrl: Ctrl, w: number, h: number,
          onScore: (s: number) => void) => () => void;
};

// ── shared control bus ───────────────────────────────────────────────────

function makeCtrl(): Ctrl & { trigger: (a: Action, kind: "down" | "up") => void } {
  const state = new Set<Action>();
  const subs = new Set<(a: Action, kind: "down" | "up") => void>();
  return {
    on(cb) { subs.add(cb); return () => subs.delete(cb); },
    pressed(a) { return state.has(a); },
    trigger(a, kind) {
      if (kind === "down") state.add(a); else state.delete(a);
      for (const s of subs) s(a, kind);
    },
  };
}

const KEY_MAP: Record<string, Action> = {
  ArrowLeft: "left", a: "left", A: "left",
  ArrowRight: "right", d: "right", D: "right",
  ArrowUp: "up", w: "up", W: "up",
  ArrowDown: "down", s: "down", S: "down",
  " ": "fire", Spacebar: "fire",
  z: "rotate", Z: "rotate", x: "rotate", X: "rotate",
};

// ── PONG ─────────────────────────────────────────────────────────────────

const pong: Game = {
  start(ctx, ctrl, w, h, onScore) {
    const PADDLE_H = 70, PADDLE_W = 8, BALL = 7, SPEED = 220, AI = 160;
    let p1 = h / 2, p2 = h / 2;
    let bx = w / 2, by = h / 2, vx = SPEED, vy = SPEED * 0.6;
    let s1 = 0, s2 = 0;
    let last = performance.now(), raf = 0;
    const loop = (t: number) => {
      const dt = Math.min(0.05, (t - last) / 1000); last = t;
      if (ctrl.pressed("up"))   p1 = Math.max(PADDLE_H / 2, p1 - SPEED * dt);
      if (ctrl.pressed("down")) p1 = Math.min(h - PADDLE_H / 2, p1 + SPEED * dt);
      // simple AI: chase ball with a cap
      if (by > p2 + 8)  p2 = Math.min(h - PADDLE_H / 2, p2 + AI * dt);
      else if (by < p2 - 8) p2 = Math.max(PADDLE_H / 2, p2 - AI * dt);
      bx += vx * dt; by += vy * dt;
      if (by < BALL || by > h - BALL) vy *= -1;
      // left paddle
      if (bx < PADDLE_W + 12 && Math.abs(by - p1) < PADDLE_H / 2 && vx < 0) {
        vx = -vx * 1.05; vy += (by - p1) * 4;
      }
      // right paddle
      if (bx > w - PADDLE_W - 12 && Math.abs(by - p2) < PADDLE_H / 2 && vx > 0) {
        vx = -vx * 1.05; vy += (by - p2) * 4;
      }
      if (bx < 0)  { s2++; onScore(s1); bx = w / 2; by = h / 2; vx = SPEED;  vy = SPEED * 0.6; }
      if (bx > w)  { s1++; onScore(s1); bx = w / 2; by = h / 2; vx = -SPEED; vy = SPEED * 0.6; }
      // draw
      ctx.fillStyle = "#0b0d10"; ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = "#2f3640"; ctx.setLineDash([4, 6]);
      ctx.beginPath(); ctx.moveTo(w / 2, 0); ctx.lineTo(w / 2, h); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#ffbf46";
      ctx.fillRect(8, p1 - PADDLE_H / 2, PADDLE_W, PADDLE_H);
      ctx.fillStyle = "#79ffe1";
      ctx.fillRect(w - 8 - PADDLE_W, p2 - PADDLE_H / 2, PADDLE_W, PADDLE_H);
      ctx.fillStyle = "#e6ebf0";
      ctx.fillRect(bx - BALL / 2, by - BALL / 2, BALL, BALL);
      ctx.font = "bold 22px JetBrains Mono, monospace";
      ctx.fillStyle = "#ffbf46"; ctx.fillText(String(s1), w / 2 - 40, 28);
      ctx.fillStyle = "#79ffe1"; ctx.fillText(String(s2), w / 2 + 22, 28);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  },
};

// ── SNAKE ────────────────────────────────────────────────────────────────

const snake: Game = {
  start(ctx, ctrl, w, h, onScore) {
    const CELL = 16;
    const cols = Math.floor(w / CELL), rows = Math.floor(h / CELL);
    let dir: [number, number] = [1, 0], next = dir;
    let body: [number, number][] = [[5, Math.floor(rows / 2)], [4, Math.floor(rows / 2)], [3, Math.floor(rows / 2)]];
    let food: [number, number] = [Math.floor(cols / 2), Math.floor(rows / 2)];
    let score = 0, dead = false;
    const off = ctrl.on((a, k) => {
      if (k !== "down") return;
      if (a === "left"  && dir[0] !== 1)  next = [-1, 0];
      if (a === "right" && dir[0] !== -1) next = [1, 0];
      if (a === "up"    && dir[1] !== 1)  next = [0, -1];
      if (a === "down"  && dir[1] !== -1) next = [0, 1];
      if (a === "fire" && dead) { dead = false; reset(); }
    });
    const reset = () => {
      dir = [1, 0]; next = dir;
      body = [[5, Math.floor(rows / 2)], [4, Math.floor(rows / 2)], [3, Math.floor(rows / 2)]];
      food = randFood(); score = 0; onScore(0);
    };
    const randFood = (): [number, number] => {
      for (let i = 0; i < 100; i++) {
        const f: [number, number] = [Math.floor(Math.random() * cols), Math.floor(Math.random() * rows)];
        if (!body.some(([x, y]) => x === f[0] && y === f[1])) return f;
      }
      return [0, 0];
    };
    let last = performance.now(), raf = 0;
    const TICK = 110;
    const loop = (t: number) => {
      if (t - last >= TICK && !dead) {
        last = t;
        dir = next;
        const [hx, hy] = body[0];
        const nx = hx + dir[0], ny = hy + dir[1];
        if (nx < 0 || ny < 0 || nx >= cols || ny >= rows ||
            body.some(([x, y]) => x === nx && y === ny)) {
          dead = true;
        } else {
          body.unshift([nx, ny]);
          if (nx === food[0] && ny === food[1]) {
            score++; onScore(score); food = randFood();
          } else {
            body.pop();
          }
        }
      }
      ctx.fillStyle = "#0b0d10"; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = "#ff6b6b";
      ctx.fillRect(food[0] * CELL + 2, food[1] * CELL + 2, CELL - 4, CELL - 4);
      for (let i = 0; i < body.length; i++) {
        ctx.fillStyle = i === 0 ? "#ffbf46" : "#7ee787";
        const [x, y] = body[i];
        ctx.fillRect(x * CELL + 1, y * CELL + 1, CELL - 2, CELL - 2);
      }
      if (dead) {
        ctx.fillStyle = "rgba(11,13,16,0.85)"; ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = "#ff6b6b";
        ctx.font = "bold 28px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText("// signal lost //", w / 2, h / 2 - 6);
        ctx.font = "13px JetBrains Mono, monospace"; ctx.fillStyle = "#b8c0ca";
        ctx.fillText("press ⊙ / space to retry", w / 2, h / 2 + 22);
        ctx.textAlign = "start";
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); off(); };
  },
};

// ── TETRIS ───────────────────────────────────────────────────────────────

const TETROMINOES: Record<string, { c: string; r: number[][][] }> = {
  I: { c: "#79ffe1", r: [
    [[1,1,1,1]],
    [[1],[1],[1],[1]],
  ]},
  O: { c: "#ffbf46", r: [[[1,1],[1,1]]] },
  T: { c: "#c779ff", r: [
    [[0,1,0],[1,1,1]], [[1,0],[1,1],[1,0]],
    [[1,1,1],[0,1,0]], [[0,1],[1,1],[0,1]],
  ]},
  L: { c: "#58a6ff", r: [
    [[0,0,1],[1,1,1]], [[1,0],[1,0],[1,1]],
    [[1,1,1],[1,0,0]], [[1,1],[0,1],[0,1]],
  ]},
  J: { c: "#ff6b6b", r: [
    [[1,0,0],[1,1,1]], [[1,1],[1,0],[1,0]],
    [[1,1,1],[0,0,1]], [[0,1],[0,1],[1,1]],
  ]},
  S: { c: "#7ee787", r: [
    [[0,1,1],[1,1,0]], [[1,0],[1,1],[0,1]],
  ]},
  Z: { c: "#c779ff", r: [
    [[1,1,0],[0,1,1]], [[0,1],[1,1],[1,0]],
  ]},
};

const tetris: Game = {
  start(ctx, ctrl, w, h, onScore) {
    const COLS = 10, ROWS = 20;
    const CELL = Math.min(Math.floor(h / ROWS), Math.floor((w * 0.55) / COLS));
    const ORIGIN_X = Math.floor((w - CELL * COLS) / 2);
    const ORIGIN_Y = Math.floor((h - CELL * ROWS) / 2);
    type Cell = string | null;
    const grid: Cell[][] = Array.from({ length: ROWS }, () => Array(COLS).fill(null) as Cell[]);
    const keys = Object.keys(TETROMINOES);
    let cur = spawn();
    let score = 0, dead = false;
    let dropAcc = 0, lastT = performance.now(), raf = 0, dropMs = 600;
    let dasL = 0, dasR = 0, softDrop = 0;

    function spawn() {
      const k = keys[Math.floor(Math.random() * keys.length)];
      const t = TETROMINOES[k];
      return { k, c: t.c, rot: 0, x: Math.floor(COLS / 2) - 1, y: 0 };
    }
    function shape(p: typeof cur) { return TETROMINOES[p.k].r[p.rot % TETROMINOES[p.k].r.length]; }
    function fits(p: typeof cur, ox = 0, oy = 0, rot = p.rot) {
      const sh = TETROMINOES[p.k].r[rot % TETROMINOES[p.k].r.length];
      for (let r = 0; r < sh.length; r++) for (let c = 0; c < sh[r].length; c++) {
        if (!sh[r][c]) continue;
        const x = p.x + c + ox, y = p.y + r + oy;
        if (x < 0 || x >= COLS || y >= ROWS) return false;
        if (y >= 0 && grid[y][x]) return false;
      }
      return true;
    }
    function lock() {
      const sh = shape(cur);
      for (let r = 0; r < sh.length; r++) for (let c = 0; c < sh[r].length; c++) {
        if (!sh[r][c]) continue;
        const y = cur.y + r;
        if (y < 0) { dead = true; return; }
        grid[y][cur.x + c] = cur.c;
      }
      // clear lines
      let cleared = 0;
      for (let r = ROWS - 1; r >= 0; r--) {
        if (grid[r].every((v) => v)) {
          grid.splice(r, 1); grid.unshift(Array(COLS).fill(null) as Cell[]);
          cleared++; r++;
        }
      }
      if (cleared) { score += [0, 100, 300, 500, 800][cleared]; onScore(score);
        dropMs = Math.max(120, 600 - Math.floor(score / 500) * 60); }
      cur = spawn();
      if (!fits(cur)) dead = true;
    }
    const off = ctrl.on((a, k) => {
      if (dead) {
        if (a === "fire" && k === "down") {
          for (const row of grid) row.fill(null);
          score = 0; onScore(0); dropMs = 600; dead = false; cur = spawn();
        }
        return;
      }
      if (k === "down") {
        if (a === "left"   && fits(cur, -1)) cur.x--;
        if (a === "right"  && fits(cur,  1)) cur.x++;
        if (a === "rotate") {
          const nr = (cur.rot + 1) % TETROMINOES[cur.k].r.length;
          if (fits(cur, 0, 0, nr)) cur.rot = nr;
          else if (fits(cur, -1, 0, nr)) { cur.x--; cur.rot = nr; }
          else if (fits(cur,  1, 0, nr)) { cur.x++; cur.rot = nr; }
        }
        if (a === "fire") { while (fits(cur, 0, 1)) cur.y++; lock(); }
        if (a === "left")  dasL = performance.now();
        if (a === "right") dasR = performance.now();
        if (a === "down")  softDrop = performance.now();
      } else {
        if (a === "left")  dasL = 0;
        if (a === "right") dasR = 0;
        if (a === "down")  softDrop = 0;
      }
    });
    const loop = (t: number) => {
      const dt = t - lastT; lastT = t;
      if (!dead) {
        // DAS auto-repeat
        if (dasL && t - dasL > 180 && fits(cur, -1)) { cur.x--; dasL = t - 120; }
        if (dasR && t - dasR > 180 && fits(cur,  1)) { cur.x++; dasR = t - 120; }
        const speed = softDrop ? 50 : dropMs;
        dropAcc += dt;
        while (dropAcc >= speed) { dropAcc -= speed;
          if (fits(cur, 0, 1)) cur.y++; else { lock(); break; }
        }
      }
      // draw
      ctx.fillStyle = "#0b0d10"; ctx.fillRect(0, 0, w, h);
      // playfield
      ctx.fillStyle = "#111418";
      ctx.fillRect(ORIGIN_X, ORIGIN_Y, CELL * COLS, CELL * ROWS);
      ctx.strokeStyle = "#2f3640";
      ctx.strokeRect(ORIGIN_X - 1, ORIGIN_Y - 1, CELL * COLS + 2, CELL * ROWS + 2);
      for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
        if (grid[r][c]) {
          ctx.fillStyle = grid[r][c] as string;
          ctx.fillRect(ORIGIN_X + c * CELL + 1, ORIGIN_Y + r * CELL + 1, CELL - 2, CELL - 2);
        }
      }
      const sh = shape(cur);
      for (let r = 0; r < sh.length; r++) for (let c = 0; c < sh[r].length; c++) {
        if (!sh[r][c]) continue;
        ctx.fillStyle = cur.c;
        ctx.fillRect(ORIGIN_X + (cur.x + c) * CELL + 1, ORIGIN_Y + (cur.y + r) * CELL + 1, CELL - 2, CELL - 2);
      }
      if (dead) {
        ctx.fillStyle = "rgba(11,13,16,0.85)"; ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = "#ff6b6b";
        ctx.font = "bold 28px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText("// stack overflow //", w / 2, h / 2 - 6);
        ctx.font = "13px JetBrains Mono, monospace"; ctx.fillStyle = "#b8c0ca";
        ctx.fillText("press ⊙ / space to retry", w / 2, h / 2 + 22);
        ctx.textAlign = "start";
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); off(); };
  },
};

// ── SPACE INVADERS ───────────────────────────────────────────────────────

const invaders: Game = {
  start(ctx, ctrl, w, h, onScore) {
    const SHIP_Y = h - 24, SHIP_W = 26, SHIP_H = 8, SHIP_SPEED = 280;
    let shipX = w / 2;
    type Bullet = { x: number; y: number; vy: number; mine: boolean };
    const bullets: Bullet[] = [];
    type Inv = { x: number; y: number; alive: boolean };
    const ROWS = 4, COLS = 8;
    let invs: Inv[] = [];
    let invDir = 1, invSpeed = 28;
    let score = 0, lives = 3, dead = false, lastShot = 0;
    function reset() {
      invs = [];
      for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
        invs.push({ x: 60 + c * 36, y: 40 + r * 26, alive: true });
      }
      invDir = 1; invSpeed = 28; bullets.length = 0;
    }
    reset();
    const off = ctrl.on((a, k) => {
      if (dead && a === "fire" && k === "down") {
        score = 0; onScore(0); lives = 3; dead = false; reset();
      }
    });
    let lastT = performance.now(), raf = 0;
    const loop = (t: number) => {
      const dt = Math.min(0.05, (t - lastT) / 1000); lastT = t;
      if (!dead) {
        if (ctrl.pressed("left"))  shipX = Math.max(SHIP_W / 2, shipX - SHIP_SPEED * dt);
        if (ctrl.pressed("right")) shipX = Math.min(w - SHIP_W / 2, shipX + SHIP_SPEED * dt);
        if (ctrl.pressed("fire") && t - lastShot > 280) {
          bullets.push({ x: shipX, y: SHIP_Y - 6, vy: -360, mine: true });
          lastShot = t;
        }
        // move invaders as a block
        let minX = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const i of invs) if (i.alive) {
          minX = Math.min(minX, i.x); maxX = Math.max(maxX, i.x); maxY = Math.max(maxY, i.y);
        }
        const dx = invDir * invSpeed * dt;
        if (minX + dx < 12 || maxX + dx > w - 12) {
          invDir *= -1;
          for (const i of invs) i.y += 12;
        } else {
          for (const i of invs) i.x += dx;
        }
        if (maxY > SHIP_Y - 16) dead = true;
        // invader fire
        if (Math.random() < 0.02) {
          const live = invs.filter((i) => i.alive);
          if (live.length) {
            const sh = live[Math.floor(Math.random() * live.length)];
            bullets.push({ x: sh.x, y: sh.y + 6, vy: 220, mine: false });
          }
        }
        // bullets
        for (const b of bullets) b.y += b.vy * dt;
        for (let bi = bullets.length - 1; bi >= 0; bi--) {
          const b = bullets[bi];
          if (b.y < -10 || b.y > h + 10) { bullets.splice(bi, 1); continue; }
          if (b.mine) {
            for (const i of invs) {
              if (i.alive && Math.abs(b.x - i.x) < 12 && Math.abs(b.y - i.y) < 10) {
                i.alive = false; bullets.splice(bi, 1);
                score += 10; onScore(score);
                invSpeed += 1.5;
                break;
              }
            }
          } else {
            if (Math.abs(b.x - shipX) < SHIP_W / 2 && b.y > SHIP_Y - SHIP_H) {
              bullets.splice(bi, 1); lives--;
              if (lives <= 0) dead = true;
            }
          }
        }
        if (invs.every((i) => !i.alive)) {
          invSpeed += 10; reset();
        }
      }
      // draw
      ctx.fillStyle = "#0b0d10"; ctx.fillRect(0, 0, w, h);
      // stars
      ctx.fillStyle = "#2f3640";
      for (let i = 0; i < 30; i++) {
        const sx = (i * 53) % w, sy = (i * 97) % h;
        ctx.fillRect(sx, sy, 1, 1);
      }
      // ship
      ctx.fillStyle = "#79ffe1";
      ctx.fillRect(shipX - SHIP_W / 2, SHIP_Y - SHIP_H, SHIP_W, SHIP_H);
      ctx.fillRect(shipX - 2, SHIP_Y - SHIP_H - 4, 4, 4);
      // invaders
      ctx.fillStyle = "#c779ff";
      for (const i of invs) if (i.alive) {
        ctx.fillRect(i.x - 10, i.y - 6, 20, 10);
        ctx.fillRect(i.x - 8, i.y + 4, 4, 3);
        ctx.fillRect(i.x + 4, i.y + 4, 4, 3);
      }
      // bullets
      for (const b of bullets) {
        ctx.fillStyle = b.mine ? "#ffbf46" : "#ff6b6b";
        ctx.fillRect(b.x - 1, b.y - 4, 2, 8);
      }
      // hud
      ctx.fillStyle = "#b8c0ca";
      ctx.font = "12px JetBrains Mono, monospace";
      ctx.fillText(`score ${score}   lives ${lives}`, 10, 16);
      if (dead) {
        ctx.fillStyle = "rgba(11,13,16,0.85)"; ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = "#ff6b6b";
        ctx.font = "bold 28px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText("// invaders won //", w / 2, h / 2 - 6);
        ctx.font = "13px JetBrains Mono, monospace"; ctx.fillStyle = "#b8c0ca";
        ctx.fillText("press ⊙ / space to retry", w / 2, h / 2 + 22);
        ctx.textAlign = "start";
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); off(); };
  },
};

// ── BREAKOUT ─────────────────────────────────────────────────────────────

const breakout: Game = {
  start(ctx, ctrl, w, h, onScore) {
    const PAD_W = 72, BALL = 6, ROWS = 5, COLS = 8, BR_H = 14, TOP = 36;
    const bw = Math.min(48, (w - 40) / COLS);
    let px = w / 2;
    let bx = w / 2, by = h - 50, bvx = 0, bvy = 0, live = false;
    const bricks: boolean[][] = Array.from({ length: ROWS }, () => Array(COLS).fill(true));
    let score = 0, lives = 3, dead = false;
    const off = ctrl.on((a, k) => {
      if (k !== "down") return;
      if (dead && a === "fire") { dead = false; lives = 3; score = 0; onScore(0);
        bricks.forEach((r) => r.fill(true)); bx = w / 2; by = h - 50; bvx = 0; bvy = 0; live = false; }
      if (!live && a === "fire") { live = true; bvx = 180 * (Math.random() > 0.5 ? 1 : -1); bvy = -220; }
    });
    let lastT = performance.now(), raf = 0;
    const loop = (t: number) => {
      const dt = Math.min(0.05, (t - lastT) / 1000); lastT = t;
      if (!dead) {
        if (ctrl.pressed("left"))  px = Math.max(PAD_W / 2, px - 320 * dt);
        if (ctrl.pressed("right")) px = Math.min(w - PAD_W / 2, px + 320 * dt);
        if (live) {
          bx += bvx * dt; by += bvy * dt;
          if (bx < BALL || bx > w - BALL) bvx *= -1;
          if (by < TOP + ROWS * BR_H) {
            const c = Math.floor((bx - (w - COLS * bw) / 2) / bw);
            const r = Math.floor((by - TOP) / BR_H);
            if (r >= 0 && r < ROWS && c >= 0 && c < COLS && bricks[r][c]) {
              bricks[r][c] = false; bvy *= -1; score += 10; onScore(score);
            }
          }
          if (by < BALL) bvy *= -1;
          if (by > h - 18 && Math.abs(bx - px) < PAD_W / 2 + BALL) {
            bvy = -Math.abs(bvy) - 20;
            bvx += (bx - px) * 3;
          }
          if (by > h) { lives--; live = false; bx = w / 2; by = h - 50; bvx = 0; bvy = 0;
            if (lives <= 0) dead = true; }
        }
      }
      ctx.fillStyle = "#0b0d10"; ctx.fillRect(0, 0, w, h);
      const ox = (w - COLS * bw) / 2;
      for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
        if (!bricks[r][c]) continue;
        ctx.fillStyle = `hsl(${(r * 40 + c * 12) % 360}, 60%, 55%)`;
        ctx.fillRect(ox + c * bw + 1, TOP + r * BR_H, bw - 2, BR_H - 2);
      }
      ctx.fillStyle = "#ffbf46";
      ctx.fillRect(px - PAD_W / 2, h - 16, PAD_W, 8);
      ctx.fillStyle = "#e6ebf0";
      ctx.fillRect(bx - BALL / 2, by - BALL / 2, BALL, BALL);
      ctx.fillStyle = "#b8c0ca";
      ctx.font = "12px JetBrains Mono, monospace";
      ctx.fillText(`score ${score}  lives ${lives}${!live && !dead ? "  ⊙ launch" : ""}`, 8, 20);
      if (dead) {
        ctx.fillStyle = "rgba(11,13,16,0.88)"; ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = "#ff6b6b"; ctx.font = "bold 24px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText("// bricks win //", w / 2, h / 2);
        ctx.textAlign = "start";
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); off(); };
  },
};

// ── ORB (catch falling signals) ──────────────────────────────────────────

const orb: Game = {
  start(ctx, ctrl, w, h, onScore) {
    const PAD_W = 56;
    let px = w / 2, score = 0, lives = 5, dead = false;
    type F = { x: number; y: number; vy: number; hue: number };
    let drops: F[] = [], spawn = 0;
    const off = ctrl.on((a, k) => {
      if (dead && a === "fire" && k === "down") { dead = false; lives = 5; score = 0; onScore(0); drops = []; }
    });
    let lastT = performance.now(), raf = 0;
    const loop = (t: number) => {
      const dt = Math.min(0.05, (t - lastT) / 1000); lastT = t;
      if (!dead) {
        if (ctrl.pressed("left"))  px = Math.max(PAD_W / 2, px - 340 * dt);
        if (ctrl.pressed("right")) px = Math.min(w - PAD_W / 2, px + 340 * dt);
        spawn += dt;
        if (spawn > 0.55) { spawn = 0;
          drops.push({ x: 20 + Math.random() * (w - 40), y: -8, vy: 80 + Math.random() * 60, hue: Math.random() * 360 });
        }
        for (let i = drops.length - 1; i >= 0; i--) {
          const d = drops[i];
          d.y += d.vy * dt;
          if (d.y > h - 22 && Math.abs(d.x - px) < PAD_W / 2 + 6) { score += 5; onScore(score); drops.splice(i, 1); continue; }
          if (d.y > h) { drops.splice(i, 1); lives--; if (lives <= 0) dead = true; }
        }
      }
      ctx.fillStyle = "#0b0d10"; ctx.fillRect(0, 0, w, h);
      for (const d of drops) {
        ctx.fillStyle = `hsl(${d.hue}, 70%, 60%)`;
        ctx.beginPath(); ctx.arc(d.x, d.y, 5, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = "#79ffe1";
      ctx.fillRect(px - PAD_W / 2, h - 14, PAD_W, 6);
      ctx.fillStyle = "#b8c0ca";
      ctx.font = "12px JetBrains Mono, monospace";
      ctx.fillText(`catch the orbs · ${score} · ${lives} misses left`, 8, 18);
      if (dead) {
        ctx.fillStyle = "rgba(11,13,16,0.88)"; ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = "#c779ff"; ctx.font = "bold 24px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText("// noise floor //", w / 2, h / 2);
        ctx.textAlign = "start";
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); off(); };
  },
};

// ── LUNAR (thrust lander) ─────────────────────────────────────────────────

const lunar: Game = {
  start(ctx, ctrl, w, h, onScore) {
    const PAD_X = w / 2, PAD_W = 44;
    let x = w / 2, y = 40, vx = 20, vy = 0;
    const G = 38, TH = 85;
    let landed = false, dead = false, fuel = 100;
    const off = ctrl.on((a, k) => {
      if (dead && a === "fire" && k === "down") {
        dead = false; landed = false; x = w / 2; y = 40; vx = 20 * (Math.random() > 0.5 ? 1 : -1); vy = 0; fuel = 100;
      }
    });
    let lastT = performance.now(), raf = 0;
    const loop = (t: number) => {
      const dt = Math.min(0.05, (t - lastT) / 1000); lastT = t;
      if (!dead && !landed) {
        if (ctrl.pressed("left"))  vx -= 70 * dt;
        if (ctrl.pressed("right")) vx += 70 * dt;
        if (ctrl.pressed("up") && fuel > 0) { vy -= TH * dt; fuel -= 28 * dt; }
        vy += G * dt; x += vx * dt; y += vy * dt;
        if (x < 8 || x > w - 8) vx *= -0.6;
        if (y > h - 36) {
          if (Math.abs(x - PAD_X) < PAD_W / 2 + 10 && Math.abs(vy) < 95) {
            landed = true; onScore(1);
          } else dead = true;
        }
      }
      ctx.fillStyle = "#0b0d10"; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = "#2f3640";
      ctx.fillRect(PAD_X - PAD_W / 2, h - 22, PAD_W, 6);
      ctx.fillStyle = landed ? "#7ee787" : "#ffbf46";
      ctx.beginPath();
      ctx.moveTo(x, y - 8); ctx.lineTo(x - 8, y + 6); ctx.lineTo(x + 8, y + 6);
      ctx.closePath(); ctx.fill();
      if (ctrl.pressed("up") && fuel > 0 && !landed && !dead) {
        ctx.strokeStyle = "#ff6b6b"; ctx.beginPath();
        ctx.moveTo(x, y + 6); ctx.lineTo(x, y + 18); ctx.stroke();
      }
      ctx.fillStyle = "#b8c0ca";
      ctx.font = "11px JetBrains Mono, monospace";
      ctx.fillText(`vx ${vx.toFixed(0)}  vy ${vy.toFixed(0)}  fuel ${fuel.toFixed(0)}  ←/→ slide  ↑ thrust`, 6, 14);
      if (landed) {
        ctx.fillStyle = "rgba(11,13,16,0.85)"; ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = "#7ee787"; ctx.font = "bold 22px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText("// soft landing //", w / 2, h / 2);
        ctx.textAlign = "start";
      }
      if (dead) {
        ctx.fillStyle = "rgba(11,13,16,0.85)"; ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = "#ff6b6b"; ctx.font = "bold 22px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText("// lithobraking //", w / 2, h / 2);
        ctx.textAlign = "start";
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); off(); };
  },
};

// ── SIGNAL (timing meter) ────────────────────────────────────────────────

const signal: Game = {
  start(ctx, ctrl, w, h, onScore) {
    let phase = 0, score = 0, streak = 0;
    const off = ctrl.on((a, k) => {
      if (k !== "down" || a !== "fire") return;
      const z = 0.5 + 0.5 * Math.sin(phase);
      if (z > 0.42 && z < 0.58) { streak++; score += 10 + streak * 5; onScore(score); }
      else { streak = 0; score = Math.max(0, score - 5); onScore(score); }
    });
    let lastT = performance.now(), raf = 0;
    const loop = (t: number) => {
      const dt = (t - lastT) / 1000; lastT = t;
      phase += dt * (1.2 + score * 0.002);
      ctx.fillStyle = "#0b0d10"; ctx.fillRect(0, 0, w, h);
      const barY = h / 2 - 10, barW = w - 80, barX = 40;
      ctx.fillStyle = "#1e232a"; ctx.fillRect(barX, barY, barW, 20);
      const gw = barW * 0.16;
      const gx = barX + barW / 2 - gw / 2;
      ctx.fillStyle = "rgba(126, 231, 135, 0.25)"; ctx.fillRect(gx, barY, gw, 20);
      const z = 0.5 + 0.5 * Math.sin(phase);
      ctx.fillStyle = "#ffbf46";
      ctx.fillRect(barX + z * (barW - 4), barY + 3, 4, 14);
      ctx.fillStyle = "#b8c0ca";
      ctx.font = "13px JetBrains Mono, monospace";
      ctx.fillText("⊙ when the pulse is in the green band", barX, barY - 12);
      ctx.fillText(`score ${score}  streak ${streak}`, barX, barY + 38);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); off(); };
  },
};

const GAMES: Record<GameId, Game> = {
  pong,
  snake,
  tetris,
  invaders,
  breakout,
  orb,
  lunar,
  signal,
};

// ── Panel ────────────────────────────────────────────────────────────────

type Props = { active: boolean };

export function GamesPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const ctrlRef = useRef(makeCtrl());
  const stopRef = useRef<(() => void) | null>(null);
  const [game, setGame] = useState<GameId>("pong");
  const [score, setScore] = useState(0);

  // boot / restart on game change or activation
  useEffect(() => {
    if (!active) return;
    const cv = canvasRef.current; if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const fit = () => {
      const rect = cv.getBoundingClientRect();
      cv.width = Math.floor(rect.width * dpr);
      cv.height = Math.floor(rect.height * dpr);
    };
    fit();
    const ctx = cv.getContext("2d"); if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    setScore(0);
    stopRef.current?.();
    stopRef.current = GAMES[game].start(
      ctx, ctrlRef.current,
      cv.width / dpr, cv.height / dpr,
      setScore,
    );
    const onResize = () => {
      fit(); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      stopRef.current?.(); stopRef.current = null;
    };
  }, [active, game]);

  // global keyboard while panel is active
  useEffect(() => {
    if (!active) return;
    const down = (e: KeyboardEvent) => {
      const a = KEY_MAP[e.key]; if (!a) return;
      e.preventDefault();
      ctrlRef.current.trigger(a, "down");
    };
    const up = (e: KeyboardEvent) => {
      const a = KEY_MAP[e.key]; if (!a) return;
      e.preventDefault();
      ctrlRef.current.trigger(a, "up");
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [active]);

  // touch button helpers — hold while pressed
  const press = (a: Action) => ({
    onPointerDown: (e: React.PointerEvent) => {
      (e.currentTarget as HTMLButtonElement).setPointerCapture(e.pointerId);
      ctrlRef.current.trigger(a, "down");
    },
    onPointerUp:    () => ctrlRef.current.trigger(a, "up"),
    onPointerCancel:() => ctrlRef.current.trigger(a, "up"),
    onPointerLeave: () => ctrlRef.current.trigger(a, "up"),
  });

  const gameList: { id: GameId; label: string }[] = [
    { id: "pong",      label: t("games.pong", "pong") },
    { id: "snake",     label: t("games.snake", "snake") },
    { id: "tetris",    label: t("games.tetris", "tetris") },
    { id: "invaders",  label: t("games.invaders", "invaders") },
    { id: "breakout",  label: t("games.breakout", "breakout") },
    { id: "orb",       label: t("games.orb", "orb") },
    { id: "lunar",     label: t("games.lunar", "lunar") },
    { id: "signal",    label: t("games.signal", "signal") },
  ];

  return (
    <div className="games-panel">
      <aside className="games-side">
        <div className="games-side-head">
          <span className="panel-glyph">◆</span> {t("games.heading", "arcade")}
        </div>
        <label className="games-picker-label">
          <span className="dim">{t("games.pickLabel", "game")}</span>
          <select
            className="games-picker"
            value={game}
            onChange={(e) => setGame(e.target.value as GameId)}
          >
            {gameList.map((g) => (
              <option key={g.id} value={g.id}>{g.label}</option>
            ))}
          </select>
        </label>
        <div className="games-score">
          <span className="dim">{t("games.score", "score")}</span>
          <span className="games-score-val">{score}</span>
        </div>
      </aside>

      <div className="games-stage">
        <canvas ref={canvasRef} className="games-canvas" />
        <div className="games-touch">
          <div className="games-dpad">
            <button className="games-tbtn games-tbtn-up"    aria-label="up"    {...press("up")}>▲</button>
            <button className="games-tbtn games-tbtn-left"  aria-label="left"  {...press("left")}>◄</button>
            <button className="games-tbtn games-tbtn-right" aria-label="right" {...press("right")}>►</button>
            <button className="games-tbtn games-tbtn-down"  aria-label="down"  {...press("down")}>▼</button>
          </div>
          <div className="games-actions">
            <button className="games-tbtn games-tbtn-rot" aria-label="rotate" {...press("rotate")}>↻</button>
            <button className="games-tbtn games-tbtn-fire" aria-label="fire"  {...press("fire")}>⊙</button>
          </div>
        </div>
      </div>
    </div>
  );
}

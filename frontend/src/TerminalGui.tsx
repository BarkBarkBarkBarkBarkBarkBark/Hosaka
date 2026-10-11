import { useEffect, useRef, useState } from "react";
import { TuiTerminal } from "./components/TuiTerminal";
import { useTranslation } from "./i18n";
import "./styles/terminal-gui.css";

type Page = "wifi" | "bluetooth" | "games" | "flash";
type WifiNetwork = { ssid: string; active: boolean; saved: boolean; signal: number | null };
type BluetoothDevice = { address: string; name: string };

async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok || result.ok === false) {
    throw new Error(result.detail ?? result.message ?? `HTTP ${response.status}`);
  }
  return result;
}

function WifiMenu() {
  const { t } = useTranslation("gui");
  const [networks, setNetworks] = useState<WifiNetwork[]>([]);
  const [ssid, setSsid] = useState("");
  const [psk, setPsk] = useState("");
  const [hidden, setHidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const result = await request<{ networks: WifiNetwork[] }>("wifi/networks");
      setNetworks(result.networks);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => { void refresh(); }, []);

  async function connect() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await request<{ message: string }>("wifi/networks", { ssid, psk, hidden });
      setPsk("");
      setMessage(result.message);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="deck-settings">
      <button disabled={busy} onClick={() => void refresh()}>{t("refresh")}</button>
      <ul className="deck-device-list">
        {networks.map((network) => (
          <li key={network.ssid}>
            <button disabled={busy} onClick={() => { setSsid(network.ssid); setPsk(""); }}>
              <span>{network.ssid}</span>
              <small>{network.active ? t("connected") : network.saved ? t("saved") : ""}
                {network.signal !== null ? ` ${network.signal}%` : ""}</small>
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={(event) => { event.preventDefault(); void connect(); }}>
        <label>{t("ssid")}<input required value={ssid} onChange={(event) => setSsid(event.target.value)} disabled={busy} /></label>
        <label>{t("password")}<input type="password" value={psk} autoComplete="off" onChange={(event) => setPsk(event.target.value)} disabled={busy} /></label>
        <label className="deck-checkbox"><input type="checkbox" checked={hidden} onChange={(event) => setHidden(event.target.checked)} disabled={busy} />{t("hiddenNetwork")}</label>
        <button type="submit" disabled={busy || !ssid.trim()}>{busy ? t("working") : t("connect")}</button>
      </form>
      {error && <p role="alert" className="deck-error">{error}</p>}
      {message && <p role="status">{message}</p>}
      <p className="deck-hint">{t("wifiHost")}</p>
    </div>
  );
}

function BluetoothMenu() {
  const { t } = useTranslation("gui");
  const [devices, setDevices] = useState<BluetoothDevice[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load(scan: boolean) {
    setBusy(true);
    setError("");
    try {
      const result = await request<{ devices: BluetoothDevice[] }>(`bluetooth/${scan ? "scan" : "devices"}`, scan ? {} : undefined);
      setDevices(result.devices);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => { void load(false); }, []);

  async function pair(address: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await request<{ message: string }>("bluetooth/pair", { address });
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="deck-settings">
      <p>{t("pairingHint")}</p>
      <button disabled={busy} onClick={() => void load(true)}>{busy ? t("working") : t("scan")}</button>
      <ul className="deck-device-list">
        {devices.map((device) => (
          <li key={device.address}>
            <span>{device.name}<small>{device.address}</small></span>
            <button disabled={busy} onClick={() => void pair(device.address)}>{t("pair")}</button>
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="deck-error">{error}</p>}
      {message && <p role="status">{message}</p>}
      <p className="deck-hint">{t("bluetoothHost")}</p>
    </div>
  );
}

function GamesMenu() {
  const { t } = useTranslation("gui");
  const [games, setGames] = useState<{ title: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const result = await request<{ games: { title: string }[] }>("games");
      setGames(result.games);
      setLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => { void refresh(); }, []);

  async function play(title?: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await request<{ message: string }>(`games/${title === undefined ? "stop" : "launch"}`, title === undefined ? {} : { title });
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="deck-settings">
      <p className="deck-hint">{t("psxLibrary")}</p>
      <div className="deck-actions">
        <button disabled={busy} onClick={() => void refresh()}>{t("refresh")}</button>
        <button disabled={busy} onClick={() => void play()}>{t("stopGame")}</button>
      </div>
      <ul className="deck-device-list">
        {games.map((game) => (
          <li key={game.title}>
            <button disabled={busy} onClick={() => void play(game.title)}>{game.title}</button>
          </li>
        ))}
      </ul>
      {busy && <p role="status">{t("working")}</p>}
      {loaded && !busy && !error && games.length === 0 && <p>{t("noGames")}</p>}
      {error && <p role="alert" className="deck-error">{error}</p>}
      {message && <p role="status">{message}</p>}
    </div>
  );
}

function FlashMenu({ onShow }: { onShow: (text: string) => void }) {
  const { t } = useTranslation("gui");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  return (
    <form className="deck-settings deck-flash-form" onSubmit={(event) => {
      event.preventDefault();
      const value = text.trim().toUpperCase() || "BUSTED";
      if (Array.from(value).length > 80 || /[\u0000-\u001f\u007f]/.test(value)) {
        setError(t("flashInvalid"));
        return;
      }
      setError("");
      onShow(value);
    }}>
      <label>{t("flashText")}<input value={text} placeholder="BUSTED" onChange={(event) => setText(event.target.value)} /></label>
      <button type="submit">{t("showFlash")}</button>
      {error && <p role="alert" className="deck-error">{error}</p>}
    </form>
  );
}

export function TerminalGui() {
  const { t } = useTranslation("gui");
  const [menu, setMenu] = useState(false);
  const [page, setPage] = useState<Page>("wifi");
  const [flash, setFlash] = useState<string | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLElement>(null);

  const close = () => {
    setMenu(false);
    button.current?.focus();
  };
  useEffect(() => {
    if (!menu) return;
    drawer.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
      } else if (event.key === "Tab" && drawer.current) {
        const focusable = Array.from(drawer.current.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), a[href]"));
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  }, [menu]);

  return (
    <main className="terminal-gui">
      <header className="deck-bar">
        <span>HOSAKA <small>{t("terminal")}</small></span>
        <button ref={button} aria-expanded={menu} aria-controls="deck-menu" onClick={() => setMenu(!menu)}>{t("menu")}</button>
      </header>
      <TuiTerminal active={!menu} flash={flash} onFlash={setFlash} />
      {menu && (
        <>
          <button className="deck-scrim" aria-label={t("close")} onClick={close} tabIndex={-1} />
          <aside className={`deck-menu${page === "games" ? " deck-menu-games" : ""}`} id="deck-menu" role="dialog" aria-modal="true" aria-label={t("menu")} ref={drawer}>
            <header><strong>{t("menu")}</strong><button onClick={close}>{t("close")}</button></header>
            <nav aria-label={t("menu")}>
              {(["wifi", "bluetooth", "games", "flash"] as const).map((item) => (
                <button key={item} aria-pressed={page === item} onClick={() => setPage(item)}>{t(item)}</button>
              ))}
            </nav>
            <div className="deck-menu-content">
              {page === "wifi" && <WifiMenu />}
              {page === "bluetooth" && <BluetoothMenu />}
              {page === "games" && <GamesMenu />}
              {page === "flash" && <FlashMenu onShow={(text) => { setMenu(false); setFlash(text); }} />}
            </div>
          </aside>
        </>
      )}
    </main>
  );
}

import i18next from "i18next";

export type CommandEntry = {
  cmd: string;
  desc: string;
  cat: string;
};

function st(key: string): string {
  return i18next.t(key, { ns: "shell" });
}

export function getCommands(): CommandEntry[] {
  return [
    { cmd: "/help",      desc: st("commands.helpDesc"),        cat: st("commands.catReference") },
    { cmd: "/commands",  desc: st("commands.commandsDesc"),    cat: st("commands.catReference") },
    { cmd: "/about",     desc: st("commands.aboutDesc"),       cat: st("commands.catReference") },
    { cmd: "/docs",      desc: st("commands.docsDesc"),        cat: st("commands.catReference") },

    { cmd: "/ask <x>",   desc: st("commands.askDesc"),         cat: st("commands.catChatAI") },
    { cmd: "/model",     desc: st("commands.modelDesc"),       cat: st("commands.catChatAI") },
    { cmd: "/reset",     desc: st("commands.resetDesc"),       cat: st("commands.catChatAI") },
    { cmd: "/settings",  desc: st("commands.settingsDesc"),    cat: st("commands.catChatAI") },

    { cmd: "/agent",         desc: st("commands.agentDesc"),       cat: st("commands.catAgent") },
    { cmd: "/agent on|off",  desc: st("commands.agentToggleDesc"), cat: st("commands.catAgent") },
    { cmd: "/agent test",    desc: st("commands.agentTestDesc"),   cat: st("commands.catAgent") },
    { cmd: "!<cmd>",         desc: st("commands.shellDesc"),       cat: st("commands.catAgent") },

    { cmd: "/netscan",   desc: st("commands.netscanDesc"),     cat: st("commands.catNetwork") },

    { cmd: "/read",      desc: st("commands.readDesc"),        cat: st("commands.catReading") },
    { cmd: "/read <slug>", desc: st("commands.readSlugDesc"),  cat: st("commands.catReading") },
    { cmd: "/read order", desc: st("commands.readOrderDesc"),  cat: st("commands.catReading") },

    { cmd: "/todo",      desc: st("commands.todoDesc"),        cat: st("commands.catOpenLoops") },
    { cmd: "/todo add <x>", desc: st("commands.todoAddDesc"),  cat: st("commands.catOpenLoops") },
    { cmd: "/todo list", desc: st("commands.todoListDesc"),    cat: st("commands.catOpenLoops") },

    { cmd: "/status",    desc: st("commands.statusDesc"),      cat: st("commands.catSystem") },
    { cmd: "/signal",    desc: st("commands.signalDesc"),      cat: st("commands.catSystem") },
    { cmd: "/clear",     desc: st("commands.clearDesc"),       cat: st("commands.catSystem") },

    { cmd: "/plant",     desc: st("commands.plantDesc"),       cat: st("commands.catTools") },
    { cmd: "/orb",       desc: st("commands.orbDesc"),         cat: st("commands.catTools") },
    { cmd: "/lore",      desc: st("commands.loreDesc"),        cat: st("commands.catTools") },
    { cmd: "/echo <x>",  desc: st("commands.echoDesc"),       cat: st("commands.catTools") },

    { cmd: "/messages",  desc: st("commands.messagesDesc"),    cat: st("commands.catPanels") },
  ];
}

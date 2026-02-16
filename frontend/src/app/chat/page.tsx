"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Send, Plus, Trash2, MessageSquare, Globe, Database, ChevronDown } from "lucide-react";
import ReactMarkdown, { type Components } from "react-markdown";
import {
  sendChatMessage,
  type ChatMessage,
  type ChatSource,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[];
}

interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string;
}

function getStorageKey(projectId?: string) {
  return projectId ? `rag-conversations-${projectId}` : "rag-conversations";
}

// ---------------------------------------------------------------------------
// Inline citation rendering
// ---------------------------------------------------------------------------

/** Parse text nodes for [N] citation markers and inject clickable links. */
function CitationText({
  text,
  sources,
}: {
  text: string;
  sources?: ChatSource[];
}) {
  if (!sources || sources.length === 0) return <>{text}</>;

  // Deduplicate sources by citation to build the index
  const uniqueSources: ChatSource[] = [];
  const seen = new Set<string>();
  for (const s of sources) {
    if (!seen.has(s.citation)) {
      seen.add(s.citation);
      uniqueSources.push(s);
    }
  }

  // Split on [N] patterns like [1], [2], [1, 2], etc.
  const parts = text.split(/(\[\d+(?:,\s*\d+)*\])/g);
  if (parts.length === 1) return <>{text}</>;

  return (
    <>
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+(?:,\s*\d+)*)\]$/);
        if (!match) return <span key={i}>{part}</span>;

        const nums = match[1].split(",").map((n) => parseInt(n.trim(), 10));
        return (
          <span key={i}>
            {nums.map((num, j) => {
              const srcIndex = num - 1; // citations are 1-indexed
              const src = uniqueSources[srcIndex];
              if (!src) {
                return (
                  <sup key={j} className="text-[10px] text-muted-foreground ml-0.5">
                    [{num}]
                  </sup>
                );
              }
              const isWeb = src.source === "perplexity";
              return (
                <a
                  key={j}
                  href={src.source_url || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={src.citation + (isWeb ? " (Web)" : " (KB)")}
                  className={`inline-flex items-center justify-center ml-0.5 no-underline rounded-full text-[10px] font-semibold h-4 min-w-4 px-1 align-super transition-colors ${
                    isWeb
                      ? "bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900/40 dark:text-blue-300"
                      : "bg-primary/10 text-primary hover:bg-primary/20"
                  }`}
                >
                  {num}
                </a>
              );
            })}
          </span>
        );
      })}
    </>
  );
}

/** Build custom ReactMarkdown components that inject citation links. */
function useCitationComponents(sources?: ChatSource[]): Components {
  return {
    p: ({ children }) => (
      <p>
        {processChildren(children, sources)}
      </p>
    ),
    li: ({ children }) => (
      <li>
        {processChildren(children, sources)}
      </li>
    ),
    td: ({ children }) => (
      <td>
        {processChildren(children, sources)}
      </td>
    ),
  };
}

/** Recursively process children to replace text nodes containing [N] markers. */
function processChildren(
  children: React.ReactNode,
  sources?: ChatSource[],
): React.ReactNode {
  if (!sources || sources.length === 0) return children;

  return Array.isArray(children)
    ? children.map((child, i) => processChild(child, sources, i))
    : processChild(children, sources, 0);
}

function processChild(
  child: React.ReactNode,
  sources: ChatSource[],
  key: number,
): React.ReactNode {
  if (typeof child === "string") {
    return <CitationText key={key} text={child} sources={sources} />;
  }
  return child;
}

const SUGGESTED_QUESTIONS = [
  "What is the M&E exemption under RCW 82.08.02565?",
  "How does the multi-point use exemption work for software licenses?",
  "Is SaaS subject to retail sales tax in Washington?",
  "When can a buyer claim a refund for over-collected sales tax?",
];

function AssistantMessage({ content, sources }: { content: string; sources?: ChatSource[] }) {
  const components = useCitationComponents(sources);
  return (
    <div className="text-sm prose prose-sm max-w-none dark:prose-invert prose-p:my-1 prose-headings:my-2 prose-li:my-0.5 prose-ul:my-1 prose-ol:my-1">
      <ReactMarkdown components={components}>{content}</ReactMarkdown>
    </div>
  );
}

function SourcesList({ sources }: { sources: ChatSource[] }) {
  const unique = sources.filter(
    (s, idx, arr) => arr.findIndex((x) => x.citation === s.citation) === idx,
  );
  return (
    <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-border/50">
      <span className="text-xs text-muted-foreground mr-1 flex items-center gap-1">
        Sources:
      </span>
      {unique.slice(0, 8).map((s, j) => {
        const isWeb = s.source === "perplexity";
        const icon = isWeb ? (
          <Globe className="h-3 w-3 mr-1 shrink-0" />
        ) : (
          <Database className="h-3 w-3 mr-1 shrink-0" />
        );
        const badge = (
          <Badge
            variant="outline"
            className={`text-xs flex items-center ${
              isWeb
                ? "border-blue-200 text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-900/30"
                : "hover:bg-primary/10"
            } ${s.source_url ? "cursor-pointer" : ""}`}
          >
            {icon}
            <span className="inline-flex items-center justify-center rounded-full bg-muted text-[10px] font-bold h-4 min-w-4 px-1 mr-1">
              {j + 1}
            </span>
            {s.citation}
            {typeof s.similarity === "number" && s.similarity > 0
              ? ` (${(s.similarity * 100).toFixed(0)}%)`
              : ""}
          </Badge>
        );
        return s.source_url ? (
          <a
            key={j}
            href={s.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex no-underline"
          >
            {badge}
          </a>
        ) : (
          <span key={j} className="inline-flex">{badge}</span>
        );
      })}
    </div>
  );
}

function loadConversations(projectId?: string): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(getStorageKey(projectId)) || "[]");
  } catch {
    return [];
  }
}

function saveConversations(convos: Conversation[], projectId?: string) {
  localStorage.setItem(getStorageKey(projectId), JSON.stringify(convos));
}

export default function ChatPage() {
  const { activeProject } = useProject();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load conversations from localStorage on mount or project change
  useEffect(() => {
    setConversations(loadConversations(activeProject?.id));
    setMessages([]);
    setActiveId(null);
  }, [activeProject?.id]);

  // Save conversations whenever they change
  const persistConversations = useCallback(
    (convos: Conversation[]) => {
      setConversations(convos);
      saveConversations(convos, activeProject?.id);
    },
    [activeProject?.id],
  );

  // Save current messages to the active conversation
  const saveCurrentMessages = useCallback(
    (msgs: Message[]) => {
      if (!activeId || msgs.length === 0) return;
      const updated = conversations.map((c) =>
        c.id === activeId ? { ...c, messages: msgs } : c,
      );
      persistConversations(updated);
    },
    [activeId, conversations, persistConversations],
  );

  function startNewConversation() {
    // Save current before switching
    if (activeId && messages.length > 0) {
      saveCurrentMessages(messages);
    }
    setMessages([]);
    setActiveId(null);
    setInput("");
  }

  function switchConversation(id: string) {
    // Save current first
    if (activeId && messages.length > 0) {
      saveCurrentMessages(messages);
    }
    const convo = conversations.find((c) => c.id === id);
    if (convo) {
      setMessages(convo.messages);
      setActiveId(id);
    }
  }

  function deleteConversation(id: string) {
    const updated = conversations.filter((c) => c.id !== id);
    persistConversations(updated);
    if (activeId === id) {
      setMessages([]);
      setActiveId(null);
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");

    // Create conversation if new
    let currentId = activeId;
    if (!currentId) {
      currentId = Date.now().toString();
      const newConvo: Conversation = {
        id: currentId,
        title: userMessage.slice(0, 60) + (userMessage.length > 60 ? "..." : ""),
        messages: [],
        createdAt: new Date().toISOString(),
      };
      const updated = [newConvo, ...conversations];
      persistConversations(updated);
      setActiveId(currentId);
    }

    // Add user message
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);

    // Add empty assistant message to stream into
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    setLoading(true);

    const history: ChatMessage[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    let sources: ChatSource[] = [];

    try {
      await sendChatMessage(
        userMessage,
        history,
        (chunk) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = {
              ...last,
              content: last.content + chunk,
              sources,
            };
            return updated;
          });
          bottomRef.current?.scrollIntoView({ behavior: "smooth" });
        },
        (s) => {
          sources = s;
        },
        activeProject?.id,
        selectedModel || undefined,
      );
      // Attach sources and save
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          sources,
        };
        // Save to localStorage
        const convos = loadConversations(activeProject?.id);
        const savedConvos = convos.map((c) =>
          c.id === currentId ? { ...c, messages: updated } : c,
        );
        saveConversations(savedConvos, activeProject?.id);
        setConversations(savedConvos);
        return updated;
      });
    } catch (err) {
      console.error(err);
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          content: "Sorry, something went wrong. Please try again.",
        };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }

  function handleSuggestedQuestion(question: string) {
    setInput(question);
    // Submit via a synthetic form event after a tick
    setTimeout(() => {
      const form = document.querySelector("form");
      if (form) form.requestSubmit();
    }, 50);
  }

  return (
    <div className="flex h-[calc(100vh-8rem)]">
      {/* Conversation sidebar */}
      <div className="w-64 border-r border-border pr-3 mr-4 flex flex-col shrink-0">
        <Button
          className="w-full mb-3 justify-start gap-2"
          onClick={startNewConversation}
        >
          <Plus className="h-4 w-4" />
          New conversation
        </Button>

        <div className="flex-1 overflow-y-auto space-y-1">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`group flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm cursor-pointer transition-colors ${
                activeId === c.id
                  ? "bg-primary/10 text-primary font-medium"
                  : "hover:bg-muted"
              }`}
              onClick={() => switchConversation(c.id)}
            >
              <MessageSquare className={`h-3.5 w-3.5 shrink-0 ${activeId === c.id ? "text-primary" : "text-muted-foreground"}`} />
              <span className="truncate flex-1">{c.title}</span>
              <button
                className="opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteConversation(c.id);
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto space-y-4 mb-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center mt-16">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 mb-4">
                <MessageSquare className="h-7 w-7 text-primary" />
              </div>
              <p className="text-lg font-semibold">
                Ask about Washington tax law
              </p>
              <p className="text-sm text-muted-foreground mt-1 mb-6">
                Your knowledge base is ready to search and answer questions.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-w-2xl">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    className="text-left text-sm border border-border rounded-xl px-4 py-3.5 hover:border-primary/30 hover:bg-primary/5 transition-all group"
                    onClick={() => handleSuggestedQuestion(q)}
                  >
                    <span className="text-muted-foreground group-hover:text-foreground transition-colors">{q}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                {msg.role === "user" ? (
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <AssistantMessage content={msg.content} sources={msg.sources} />
                )}
                {msg.role === "assistant" &&
                  msg.sources &&
                  msg.sources.length > 0 && (
                    <SourcesList sources={msg.sources} />
                  )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSend} className="flex gap-2">
          <div className="relative shrink-0">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="h-9 appearance-none rounded-lg border border-input bg-background pl-3 pr-8 text-xs cursor-pointer hover:border-primary/40 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50"
            >
              <option value="">Auto</option>
              <option value="claude-haiku-4-5-20251001">Haiku (Fast)</option>
              <option value="claude-sonnet-4-5-20250929">Sonnet (Balanced)</option>
              <option value="claude-opus-4-6">Opus (Deep)</option>
              <option value="gpt-5.2">GPT-5.2</option>
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          </div>
          <Input
            placeholder="Ask about Washington tax law..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            className="flex-1 focus-visible:ring-primary/30 focus-visible:border-primary/50"
          />
          <Button type="submit" disabled={loading || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </div>
    </div>
  );
}

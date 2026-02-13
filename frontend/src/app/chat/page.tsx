"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Send, Plus, Trash2, MessageSquare } from "lucide-react";
import ReactMarkdown from "react-markdown";
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

const SUGGESTED_QUESTIONS = [
  "What is the M&E exemption under RCW 82.08.02565?",
  "How does the multi-point use exemption work for software licenses?",
  "Is SaaS subject to retail sales tax in Washington?",
  "When can a buyer claim a refund for over-collected sales tax?",
];

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
                  <div className="text-sm prose prose-sm max-w-none dark:prose-invert prose-p:my-1 prose-headings:my-2 prose-li:my-0.5 prose-ul:my-1 prose-ol:my-1">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                )}
                {msg.role === "assistant" &&
                  msg.sources &&
                  msg.sources.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3 pt-2 border-t border-border/50">
                      <span className="text-xs text-muted-foreground mr-1">
                        Sources:
                      </span>
                      {msg.sources
                        .filter(
                          (s, idx, arr) =>
                            arr.findIndex((x) => x.citation === s.citation) === idx,
                        )
                        .slice(0, 6)
                        .map((s, j) =>
                          s.source_url ? (
                            <a
                              key={j}
                              href={s.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex"
                            >
                              <Badge variant="outline" className="text-xs hover:bg-primary/10 cursor-pointer">
                                {s.citation}
                                {typeof s.similarity === "number" && s.similarity > 0
                                  ? ` (${(s.similarity * 100).toFixed(0)}%)`
                                  : ""}
                              </Badge>
                            </a>
                          ) : (
                            <Badge key={j} variant="outline" className="text-xs">
                              {s.citation}
                              {typeof s.similarity === "number" && s.similarity > 0
                                ? ` (${(s.similarity * 100).toFixed(0)}%)`
                                : ""}
                            </Badge>
                          ),
                        )}
                    </div>
                  )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSend} className="flex gap-2">
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

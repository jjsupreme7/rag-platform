"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Plus, Trash2, Save, AlertTriangle } from "lucide-react";
import { useProject } from "@/lib/project-context";
import { createProject, updateProject, deleteProject } from "@/lib/api";

export default function SettingsPage() {
  const { activeProject, projects, refreshProjects, setActiveProject } = useProject();

  const [name, setName] = useState(activeProject?.name || "");
  const [description, setDescription] = useState(activeProject?.description || "");
  const [systemPrompt, setSystemPrompt] = useState(activeProject?.system_prompt || "");
  const [chatModel, setChatModel] = useState(activeProject?.chat_model || "gpt-5.2");
  const [embeddingModel, setEmbeddingModel] = useState(activeProject?.embedding_model || "text-embedding-3-small");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState("");

  // Sync form when active project changes
  const [lastProjectId, setLastProjectId] = useState(activeProject?.id);
  if (activeProject?.id !== lastProjectId) {
    setLastProjectId(activeProject?.id);
    setName(activeProject?.name || "");
    setDescription(activeProject?.description || "");
    setSystemPrompt(activeProject?.system_prompt || "");
    setChatModel(activeProject?.chat_model || "gpt-5.2");
    setEmbeddingModel(activeProject?.embedding_model || "text-embedding-3-small");
    setMessage("");
  }

  async function handleSave() {
    if (!activeProject) return;
    setSaving(true);
    setMessage("");
    try {
      await updateProject(activeProject.id, {
        name,
        description,
        system_prompt: systemPrompt,
        chat_model: chatModel,
        embedding_model: embeddingModel,
      });
      await refreshProjects();
      setMessage("Saved successfully");
    } catch (e) {
      setMessage(`Error: ${e}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateProject() {
    if (!newName.trim()) return;
    setSaving(true);
    try {
      const p = await createProject({ name: newName.trim() });
      await refreshProjects();
      setActiveProject(p);
      setNewName("");
      setShowNewForm(false);
      setMessage("Project created");
    } catch (e) {
      setMessage(`Error: ${e}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!activeProject) return;
    if (!confirm(`Delete "${activeProject.name}"? This cannot be undone.`)) return;
    setSaving(true);
    try {
      await deleteProject(activeProject.id);
      await refreshProjects();
      setMessage("Project deleted");
    } catch (e) {
      setMessage(`Error: ${e}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Project Settings</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Configure your project and AI models.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowNewForm(!showNewForm)}
        >
          <Plus className="h-4 w-4 mr-1" />
          New Project
        </Button>
      </div>

      {/* New project form */}
      {showNewForm && (
        <Card className="mb-6 border-primary/20">
          <CardHeader>
            <CardTitle className="text-base">Create New Project</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                placeholder="Project name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="focus-visible:ring-primary/30 focus-visible:border-primary/50"
              />
              <Button onClick={handleCreateProject} disabled={!newName.trim() || saving}>
                Create
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {activeProject ? (
        <div className="space-y-6">
          {/* General settings */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">General</CardTitle>
              <CardDescription>Basic project information</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1.5 block">Name</label>
                <Input value={name} onChange={(e) => setName(e.target.value)} className="focus-visible:ring-primary/30 focus-visible:border-primary/50" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1.5 block">Description</label>
                <Input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of this project"
                  className="focus-visible:ring-primary/30 focus-visible:border-primary/50"
                />
              </div>
            </CardContent>
          </Card>

          {/* AI Configuration */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">AI Configuration</CardTitle>
              <CardDescription>System prompt and model settings</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1.5 block">System Prompt</label>
                <textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  rows={6}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 transition-colors"
                  placeholder="Instructions for the AI assistant in this project..."
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Chat Model</label>
                  <select
                    value={chatModel}
                    onChange={(e) => setChatModel(e.target.value)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm cursor-pointer hover:border-primary/40 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50"
                  >
                    <option value="gpt-5.2">GPT-5.2</option>
                    <option value="gpt-4o">GPT-4o</option>
                    <option value="gpt-4o-mini">GPT-4o-mini</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Embedding Model</label>
                  <select
                    value={embeddingModel}
                    onChange={(e) => setEmbeddingModel(e.target.value)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm cursor-pointer hover:border-primary/40 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50"
                  >
                    <option value="text-embedding-3-small">text-embedding-3-small</option>
                    <option value="text-embedding-3-large">text-embedding-3-large</option>
                  </select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Save */}
          <div className="flex items-center gap-3">
            <Button onClick={handleSave} disabled={saving}>
              <Save className="h-4 w-4 mr-1.5" />
              {saving ? "Saving..." : "Save Changes"}
            </Button>
            {message && (
              <p className={`text-sm ${message.startsWith("Error") ? "text-red-500" : "text-emerald-600"}`}>
                {message}
              </p>
            )}
          </div>

          {/* Danger zone */}
          {projects.length > 1 && (
            <Card className="border-red-200">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2 text-red-600">
                  <AlertTriangle className="h-4 w-4" />
                  Danger Zone
                </CardTitle>
                <CardDescription>Irreversible actions for this project</CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleDelete}
                  disabled={saving}
                >
                  <Trash2 className="h-4 w-4 mr-1.5" />
                  Delete Project
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Project info */}
          <div className="pt-2 text-xs text-muted-foreground/60 space-y-0.5">
            <p>Project ID: {activeProject.id}</p>
            <p>Created: {new Date(activeProject.created_at).toLocaleDateString()}</p>
          </div>
        </div>
      ) : (
        <p className="text-muted-foreground">No project selected.</p>
      )}
    </div>
  );
}

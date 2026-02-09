"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Plus, Trash2, Save } from "lucide-react";
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
        <h2 className="text-2xl font-bold">Project Settings</h2>
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
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">Create New Project</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                placeholder="Project name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <Button onClick={handleCreateProject} disabled={!newName.trim() || saving}>
                Create
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {activeProject ? (
        <div className="space-y-4">
          {/* Name */}
          <div>
            <label className="text-sm font-medium mb-1 block">Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          {/* Description */}
          <div>
            <label className="text-sm font-medium mb-1 block">Description</label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this project"
            />
          </div>

          {/* System Prompt */}
          <div>
            <label className="text-sm font-medium mb-1 block">System Prompt</label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={6}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="Instructions for the AI assistant in this project..."
            />
          </div>

          {/* Models */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-1 block">Chat Model</label>
              <select
                value={chatModel}
                onChange={(e) => setChatModel(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="gpt-5.2">GPT-5.2</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-4o-mini">GPT-4o-mini</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Embedding Model</label>
              <select
                value={embeddingModel}
                onChange={(e) => setEmbeddingModel(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="text-embedding-3-small">text-embedding-3-small</option>
                <option value="text-embedding-3-large">text-embedding-3-large</option>
              </select>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3 pt-2">
            <Button onClick={handleSave} disabled={saving}>
              <Save className="h-4 w-4 mr-1" />
              {saving ? "Saving..." : "Save Changes"}
            </Button>
            {projects.length > 1 && (
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDelete}
                disabled={saving}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Delete Project
              </Button>
            )}
          </div>

          {/* Status message */}
          {message && (
            <p className={`text-sm ${message.startsWith("Error") ? "text-red-500" : "text-green-600"}`}>
              {message}
            </p>
          )}

          {/* Project info */}
          <div className="pt-4 border-t">
            <p className="text-xs text-muted-foreground">
              Project ID: {activeProject.id}
            </p>
            <p className="text-xs text-muted-foreground">
              Created: {new Date(activeProject.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      ) : (
        <p className="text-muted-foreground">No project selected.</p>
      )}
    </div>
  );
}

"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, Field, notify } from "@sendora/ui-kit";
import { PageHead, Textarea } from "@/components/Parts";
import { post } from "@/lib/api";
import { useRole } from "@/lib/hooks";

/** The form that makes a voice: the person or brand whose writing the drafts should sound like. A new install has none until one is added here. */
export function AddVoice() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const [name, setName] = useState("");
  const [about, setAbout] = useState("");
  const add = useMutation({
    mutationFn: () => post<{ id: number }>("/authors", { name: name.trim(), about: about.trim() }),
    onSuccess: () => { notify.success("Voice added. Next, add some of their writing in the Library."); setName(""); setAbout(""); qc.invalidateQueries(); },
    onError: (e: Error) => notify.error("Could not add the voice", e.message),
  });
  return (
    <Card title="Add a voice">
      <div className="vp-stack">
        <Field label="Name" value={name} onChange={setName} maxLength={120} hint="A person or a brand, for example Sam Rivera." />
        <Textarea label="About this voice (optional)" value={about} maxLength={2000} onChange={(e) => setAbout(e.target.value)} hint="Who they write for and what they write about." />
        <Button variant="primary" disabled={!canWrite || name.trim().length < 2} disabledReason={!canWrite ? "Viewers cannot change anything" : "Type a name"} onClick={async () => { await add.mutateAsync().catch(() => null); }}>Add voice</Button>
      </div>
    </Card>
  );
}

/** Shown on a page that needs a voice when there is none yet. */
export function NoVoices({ title }: { title: string }) {
  return (
    <div className="vp-page">
      <PageHead title={title} sub="Start by adding a voice: the person or brand whose writing your drafts should sound like. Then add some of their writing and build the profile." />
      <AddVoice />
    </div>
  );
}

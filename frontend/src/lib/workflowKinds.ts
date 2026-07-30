/**
 * Turning the configured workflow kinds into what the Create sidebar shows.
 *
 * Kinds are data (Configure › Types), so everything here is derivation rather
 * than a table of cases: the Workflow Type select lists the distinct groups, the
 * Mode select lists the kinds inside the chosen group and disappears when there
 * is only one, and the Workflow select is filtered by each file's tags.
 */
import type { WorkflowKind, WorkflowTagMap } from '@/types'

/** Used until the kinds request lands, so the sidebar never renders empty. */
export const FALLBACK_KIND: WorkflowKind = {
  value: 'image_generation.i2i',
  label: 'I2I — from a source image',
  group: 'image_generation',
  group_label: 'Image Generation',
  needs_image: true,
  uses_text: true,
  uses_ai: true,
  hint: '',
}

export interface KindGroup {
  value: string
  label: string
}

/** The distinct groups, in the order the kinds declare them. */
export const groupsOf = (kinds: WorkflowKind[]): KindGroup[] => {
  const seen = new Map<string, string>()
  for (const kind of kinds) {
    if (!seen.has(kind.group)) seen.set(kind.group, kind.group_label || kind.group)
  }
  return [...seen].map(([value, label]) => ({ value, label }))
}

export const kindsInGroup = (kinds: WorkflowKind[], group: string): WorkflowKind[] =>
  kinds.filter(k => k.group === group)

/**
 * Resolve a remembered kind value against the current vocabulary.
 *
 * Falls back through: the exact value, a kind in the same group, a bare legacy
 * suffix ('i2i' — what the last-used config stored before kinds existed), then
 * the first kind of the group, then the first kind at all. The point is that a
 * renamed or deleted kind leaves the sidebar usable rather than blank.
 */
export const resolveKind = (
  kinds: WorkflowKind[],
  saved: string | undefined,
  group?: string,
): WorkflowKind => {
  const pool = group ? kindsInGroup(kinds, group) : kinds
  const candidates = pool.length > 0 ? pool : kinds
  if (saved) {
    const exact = candidates.find(k => k.value === saved)
    if (exact) return exact
    // 'i2i' should still find 'image_generation.i2i'.
    const suffix = candidates.find(k => k.value.split('.').pop() === saved)
    if (suffix) return suffix
  }
  return candidates[0] ?? kinds[0] ?? FALLBACK_KIND
}

export interface WorkflowChoices {
  /** Files tagged with the selected kind — the ones that fit. */
  matching: string[]
  /**
   * Files with no tags at all. Listed under their own heading rather than
   * hidden: a freshly imported workflow is untagged, and dropping it from the
   * list would make it look like the import failed.
   */
  untagged: string[]
}

/**
 * Split the workflow files into the ones that suit `kindValue` and the ones
 * nobody has tagged. Files tagged for *other* kinds are excluded — that is the
 * whole point of tagging them.
 */
export const workflowChoices = (
  workflows: string[],
  tags: WorkflowTagMap,
  kindValue: string,
): WorkflowChoices => {
  const matching: string[] = []
  const untagged: string[] = []
  for (const name of workflows) {
    const entry = tags[name]
    if (!entry || entry.kinds.length === 0) untagged.push(name)
    else if (entry.kinds.includes(kindValue)) matching.push(name)
  }
  return { matching, untagged }
}

/**
 * Which workflow the sidebar should have selected: the remembered one when it
 * still suits the kind, else the first that does, else the first untagged file.
 */
export const pickWorkflow = (
  choices: WorkflowChoices,
  remembered: string | undefined,
): string => {
  const all = [...choices.matching, ...choices.untagged]
  if (remembered && all.includes(remembered)) return remembered
  return choices.matching[0] ?? choices.untagged[0] ?? ''
}

/**
 * The input names ComfyUI text nodes use — mirrors PROMPT_INPUT_KEYS in
 * backend/pipelines/image.py. CLIPTextEncode calls it `text`; Qwen's
 * TextEncodeQwenImageEditPlus calls it `prompt`, which is why detection alone
 * cannot find it.
 */
export const PROMPT_INPUT_KEYS = ['text', 'prompt'] as const

/** Candidate nodes for a binding: those with a literal (unwired) input `key`. */
export const nodesWithInput = (
  graph: Record<string, { class_type?: string; inputs?: Record<string, unknown>; _meta?: { title?: string } }> | null,
  keys: string | readonly string[],
): Array<{ id: string; label: string }> => {
  if (!graph) return []
  const wanted = typeof keys === 'string' ? [keys] : keys
  return Object.entries(graph)
    .filter(([, node]) =>
      wanted.some(key => {
        const value = node?.inputs?.[key]
        // An array value is a wire from another node, not an editable input.
        return value !== undefined && !Array.isArray(value)
      }),
    )
    .map(([id, node]) => ({
      id,
      label: `${id} · ${node._meta?.title || node.class_type || 'node'}`,
    }))
}

import { describe, expect, it } from 'vitest'

import {
  groupsOf, kindsInGroup, nodesWithInput, pickWorkflow, resolveKind, workflowChoices,
} from '@/lib/workflowKinds'
import type { WorkflowKind, WorkflowTagMap } from '@/types'

const kind = (over: Partial<WorkflowKind> & { value: string }): WorkflowKind => ({
  label: over.value,
  group: over.value.split('.')[0],
  group_label: over.value.split('.')[0],
  needs_image: true,
  uses_text: true,
  uses_ai: false,
  hint: '',
  ...over,
})

const KINDS: WorkflowKind[] = [
  kind({ value: 'image_generation.i2i', group_label: 'Image Generation' }),
  kind({ value: 'image_generation.t2i', group_label: 'Image Generation', needs_image: false }),
  kind({ value: 'image_upscaler', group_label: 'Image Upscaler', uses_text: false }),
]

describe('groupsOf', () => {
  it('collapses kinds into their groups, keeping declaration order', () => {
    expect(groupsOf(KINDS)).toEqual([
      { value: 'image_generation', label: 'Image Generation' },
      { value: 'image_upscaler', label: 'Image Upscaler' },
    ])
  })

  it('lists the modes of one group', () => {
    expect(kindsInGroup(KINDS, 'image_generation').map(k => k.value)).toEqual([
      'image_generation.i2i',
      'image_generation.t2i',
    ])
  })
})

describe('resolveKind', () => {
  it('takes the exact value when it still exists', () => {
    expect(resolveKind(KINDS, 'image_generation.t2i').value).toBe('image_generation.t2i')
  })

  it('accepts a bare mode written by an earlier build', () => {
    // The last-used config stored 't2i' before kinds were configurable.
    expect(resolveKind(KINDS, 't2i').value).toBe('image_generation.t2i')
  })

  it('falls back to the group first kind when the saved one is gone', () => {
    expect(resolveKind(KINDS, 'image_generation.inpaint', 'image_generation').value)
      .toBe('image_generation.i2i')
  })

  it('stays inside the requested group', () => {
    // A remembered t2i must not survive a switch to a different type.
    expect(resolveKind(KINDS, 'image_generation.t2i', 'image_upscaler').value)
      .toBe('image_upscaler')
  })

  it('yields a usable kind when the vocabulary is empty', () => {
    expect(resolveKind([], 'anything').value).toBe('image_generation.i2i')
  })
})

describe('workflowChoices', () => {
  const files = ['ZIB-ZIT.json', 'Z-image-control-net.json', 'SeedVR.json', 'fresh-import.json']
  const tags: WorkflowTagMap = {
    'ZIB-ZIT.json': { kinds: ['image_generation.t2i'], prompt_node: '21', image_node: null },
    'Z-image-control-net.json': { kinds: ['image_generation.i2i'] },
    'SeedVR.json': { kinds: ['image_upscaler'] },
  }

  it('keeps only the files tagged for the kind', () => {
    expect(workflowChoices(files, tags, 'image_generation.t2i').matching).toEqual(['ZIB-ZIT.json'])
  })

  it('lists untagged files separately rather than hiding them', () => {
    // A fresh import has no tags; dropping it would look like a failed import.
    const { matching, untagged } = workflowChoices(files, tags, 'image_upscaler')
    expect(matching).toEqual(['SeedVR.json'])
    expect(untagged).toEqual(['fresh-import.json'])
  })

  it('treats an empty kinds list as untagged', () => {
    const { untagged } = workflowChoices(['a.json'], { 'a.json': { kinds: [] } }, 'image_upscaler')
    expect(untagged).toEqual(['a.json'])
  })
})

describe('pickWorkflow', () => {
  const choices = { matching: ['tagged.json'], untagged: ['loose.json'] }

  it('keeps the remembered file when it is still on offer', () => {
    expect(pickWorkflow(choices, 'loose.json')).toBe('loose.json')
  })

  it('drops a remembered file that no longer suits the kind', () => {
    expect(pickWorkflow(choices, 'other-kind.json')).toBe('tagged.json')
  })

  it('falls back to an untagged file when nothing is tagged', () => {
    expect(pickWorkflow({ matching: [], untagged: ['loose.json'] }, undefined)).toBe('loose.json')
  })

  it('returns empty when there are no workflows at all', () => {
    expect(pickWorkflow({ matching: [], untagged: [] }, 'x.json')).toBe('')
  })
})

describe('nodesWithInput', () => {
  const graph = {
    '21': { class_type: 'CLIPTextEncode', inputs: { text: 'a prompt', clip: ['25', 0] } },
    '28': { class_type: 'ConditioningZeroOut', inputs: { conditioning: ['21', 0] } },
    '12': { class_type: 'LoadImage', inputs: { image: 'ref.png' }, _meta: { title: 'Source' } },
    '30': { class_type: 'ImageBlend', inputs: { image: ['12', 0] } },
  }

  it('offers the nodes with a literal input of that name', () => {
    expect(nodesWithInput(graph, 'text')).toEqual([
      { id: '21', label: '21 · CLIPTextEncode' },
    ])
  })

  it('skips inputs that are wired from another node', () => {
    // ['12', 0] is a wire, not something the dispatcher can write to.
    expect(nodesWithInput(graph, 'image')).toEqual([{ id: '12', label: '12 · Source' }])
  })

  it('handles a graph that failed to parse', () => {
    expect(nodesWithInput(null, 'text')).toEqual([])
  })
})

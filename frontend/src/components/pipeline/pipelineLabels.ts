const STEP_LABELS: Record<string, string> = {
  vision_observation: 'Vision observation',
  prompt_writer: 'Prompt Writer',
  analyst: 'Analyst',
  turbo_engineer: 'Turbo Engineer',
}

export function pipelineStepLabel(stepKey: string) {
  return STEP_LABELS[stepKey] ?? stepKey.replaceAll('_', ' ')
}

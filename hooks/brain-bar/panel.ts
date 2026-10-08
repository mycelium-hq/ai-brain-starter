// The «¿Qué piensa el panel?» button of the brain-bar band. Pure: the band
// hook in hooks/register.tsx decides with these and submits the prompt.

export type Locale = 'es' | 'en'

// The prompt the button submits as the person's own words, and its label.
export const panelPrompt = (locale: Locale): string => (locale === 'es' ? '¿Qué piensa el panel?' : 'What does the panel think?')

// The roster every install gets at setup (phases/phase-10b-panel-roster.md),
// read by the coaching skill at <Meta>/rules/advisory-panel.md.
export const ROSTER_PATH = ['rules', 'advisory-panel.md'] as const

export type PanelFacts = {
  // Replies the model has given this session: before the first there is
  // nothing for the panel to weigh in on.
  replies: number
  // A turn is running: a prompt submitted now would wait unseen in a queue.
  isWorking: boolean
  // Without a roster the model would invent its advisors.
  hasRoster: boolean
}

export const showPanelButton = (facts: PanelFacts): boolean => facts.replies > 0 && !facts.isWorking && facts.hasRoster

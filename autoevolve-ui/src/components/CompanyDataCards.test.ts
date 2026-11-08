import { describe, expect, it } from 'vitest'
import { ANSWERS, CANONICAL_QUESTIONS } from './CompanyDataCards'

describe('shared company-fact copy', () => {
  it('covers every canonical group the completeness gate reads', () => {
    for (const key of ['company', 'product', 'customer', 'problem', 'objective', 'marketing_stage']) {
      expect(Object.keys(ANSWERS)).toContain(key)
      expect(ANSWERS[key].question.length).toBeGreaterThan(0)
    }
  })

  it('asks the same questions in onboarding and commercial', () => {
    // section.key pairs must match core.company_context._ONBOARDING_SECTIONS
    // so both editors write the same canonical facts.
    expect(CANONICAL_QUESTIONS.description).toMatchObject({ section: 'company', key: 'description' })
    expect(CANONICAL_QUESTIONS.industry).toMatchObject({ section: 'customer', key: 'industry' })
    expect(CANONICAL_QUESTIONS.positioning).toMatchObject({ section: 'product', key: 'value_proposition' })
    expect(CANONICAL_QUESTIONS.offer_summary).toMatchObject({ section: 'offer', key: 'description' })
    expect(CANONICAL_QUESTIONS.ideal_customer).toMatchObject({ section: 'customer', key: 'ideal_customer' })
    expect(CANONICAL_QUESTIONS.problem).toMatchObject({ section: 'market', key: 'problem' })
    for (const entry of Object.values(CANONICAL_QUESTIONS)) {
      expect(entry.question.length).toBeGreaterThan(0)
      expect(entry.example.length).toBeGreaterThan(0)
      expect(entry.help.length).toBeGreaterThan(0)
    }
  })

  it('commercial cards reuse the shared copy', () => {
    expect(ANSWERS.company.question).toBe(CANONICAL_QUESTIONS.description.question)
    expect(ANSWERS.customer.question).toBe(CANONICAL_QUESTIONS.ideal_customer.question)
    expect(ANSWERS.problem.question).toBe(CANONICAL_QUESTIONS.problem.question)
  })
})

Remove AI writing patterns from a cover letter, application answer, or any professional text.

Before starting:
1. Read CLAUDE.md Writing Voice Rules for the baseline constraints.
2. Read resume/knowledge-base.md briefly to know what real specifics are available if a vague sentence could be grounded.

**No-fabrication rule (absolute):** Do not add any fact, metric, tool, company name, date, or claim that is not in the source text or explicitly provided by the user. If a sentence needs real detail to work, ask for it or write the plain version without it.

**Process:**
1. Scan the input and identify every AI pattern present (list them briefly).
2. Write a draft rewrite.
3. Ask: "What still reads as AI-generated?" Answer in 2–3 bullets.
4. Produce the final rewrite. Before returning it, scan for em dashes (— or –) — any hit means the draft is not done.

**Output format:**
- **Patterns found:** (short list)
- **Draft rewrite**
- **Still sounds AI because:** (2–3 bullets)
- **Final rewrite**

---

## Pattern Reference

### CONTENT PATTERNS

**1. Inflated significance**
Words to cut: stands as, serves as, is a testament to, pivotal, underscores, reflects broader, symbolizing, contributing to, setting the stage for, marks a shift, evolving landscape, indelible mark
Fix: say what happened, not what it symbolizes.

**2. Undue notability claims**
Words to cut: independent coverage, active social media presence, written by a leading expert
Fix: state the actual fact or cut the sentence.

**3. -ing tailing phrases**
Words to cut: highlighting..., underscoring..., reflecting..., symbolizing..., fostering..., showcasing..., contributing to..., cultivating...
Fix: end the sentence before the tacked-on participle. If the idea matters, make it its own sentence.
> Before: Led the LATAM team, fostering cross-cultural collaboration and contributing to revenue growth.
> After: Led the LATAM team across 3 countries.

**4. Promotional language**
Words to cut: boasts, vibrant, rich (figurative), profound, nestled, in the heart of, groundbreaking, renowned, breathtaking, stunning, commitment to excellence
Fix: plain declarative sentence.
> Before: A vibrant professional with a rich track record and a profound commitment to excellence.
> After: Sixteen years of digital marketing across agencies, SaaS, and streaming.

**5. Vague attributions**
Phrases to cut: industry reports show, experts argue, observers have noted, several sources suggest
Fix: name the actual source or cut the claim.

**6. Formulaic challenges sections**
Patterns to cut: "Despite X challenges, Y continues to thrive", "Despite this, the future looks bright"
Fix: state the specific fact or cut the section.

---

### LANGUAGE PATTERNS

**7. AI vocabulary**
Cut these words on sight: actually, additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (verb), interplay, intricate/intricacies, key (adjective), landscape (abstract), pivotal, showcase, tapestry, testament, underscore, valuable, vibrant
> Before: This role aligns with my key strengths and will allow me to delve into intricate SEO challenges.
> After: This role matches what I've spent 16 years building.

**8. Copula avoidance**
Words to cut: serves as, stands as, marks, represents [a], boasts, features, offers [a]
Fix: use is/are/has.
> Before: My career serves as a testament to cross-border collaboration.
> After: I've worked across Brazil, India, Argentina, the Netherlands, and Spain.

**9. Negative parallelisms**
Patterns to cut: "Not only X but also Y", "It's not just about X, it's about Y", "Not merely X but Z"
Fix: say the main point directly.
> Before: This isn't just about SEO. It's about building content that actually converts.
> After: The work is SEO content that converts.

**10. Rule of three**
Pattern: X, Y, and Z where three examples are forced together for effect.
Fix: use one or two; the third is almost always padding.
> Before: I bring creativity, strategic thinking, and a passion for results.
> After: I bring 16 years of campaign strategy across four countries.

**11. Synonym cycling**
Pattern: referring to the same thing with a different word each sentence to avoid repetition.
Fix: repeat the clearest word; don't swap synonyms mechanically.

**12. False ranges**
Pattern: "from X to Y" where X and Y aren't on a meaningful scale.
> Before: My experience spans from social media to C-suite stakeholder reporting.
> After: I've run social campaigns and reported results to executives.

**13. Passive voice and subjectless fragments**
Pattern: "No cover letter required." "Results were delivered on time."
Fix: name the actor.
> Before: Strong results were achieved throughout the engagement.
> After: The campaign delivered 22,000 leads in 7 days.

---

### STYLE PATTERNS

**14. Em dashes — cut all of them**
The em dash (—) and en dash (–) are among the most reliable AI tells. Treat this as a hard constraint.
Replace with: a period (start a new sentence), a comma (tight aside), a colon (introducing an explanation), or parentheses (true aside).
Before returning the final rewrite, search for — and –. Any hit means the draft is not done.
> Before: My work at Canva — which spanned 4 years — covered 100% of SEO for Brazil.
> After: My work at Canva covered 4 years and 100% of SEO production for Brazil.

**15. Excessive boldface**
Pattern: bolding words mechanically throughout prose.
Fix: remove bold unless it's a genuine document heading.

**16. Inline-header bullet lists**
Pattern: bullets starting with **Label:** description.
Fix: convert to prose, or use plain bullets without the bolded label.
> Before: **Result:** Increased leads by 2x. **Cost:** 40% reduction in CPL.
> After: Lead volume doubled and cost per lead dropped 40%.

**17. Title case in headings**
Pattern: Every Word Capitalized In A Heading
Fix: sentence case only.

**18. Emojis in professional text**
Cut all emojis from cover letters and application answers.

---

### COMMUNICATION PATTERNS

**19. Chatbot artifacts**
Phrases to cut: I hope this helps, Of course!, Certainly!, Would you like me to, Let me know if, Here is a summary of
Fix: just say the thing.

**20. Sycophantic openers**
Phrases to cut: I am thrilled/excited/passionate/honored to apply, Great question, You're absolutely right, That's an excellent point
Fix: start with a specific fact or claim.
> Before: I am thrilled to apply for this role and passionate about SEO.
> After: I've owned SEO content for Canva Brazil's 200M-user market for four years.

---

### FILLER AND HEDGING

**21. Filler phrases**
- "in order to" → "to"
- "due to the fact that" → "because"
- "at this point in time" → "now"
- "in the event that" → "if"
- "has the ability to" → "can"
- "it is important to note that" → delete it; just say the thing

**22. Excessive hedging**
Pattern: "could potentially possibly be argued that it might have some effect"
Fix: say what you mean.

**23. Generic positive conclusions**
Pattern: "The future looks bright", "Exciting times ahead", "A major step in the right direction"
Fix: cut the paragraph. End on the last concrete fact.

**24. Hyphenated compounds in predicate position**
Fix: drop the hyphen when the compound follows the noun.
> Before: My approach is data-driven and results-oriented.
> After: My approach is data driven and results oriented.

**25. Persuasive authority tropes**
Phrases to cut: the real question is, at its core, in reality, what really matters, fundamentally, the deeper issue, the heart of the matter
Fix: say the ordinary point without the ceremony.

**26. Signposting**
Phrases to cut: Let's dive in, let's explore, let's break this down, here's what you need to know, without further ado
Fix: just do the thing you were about to announce.

**27. Fragmented headers**
Pattern: heading followed by a one-line restatement of the heading before the real content.
Fix: cut the warm-up line; start with the content.

**28. Staccato drama**
Pattern: run of short emphatic fragments meant to sound impactful.
> Before: Then the results came in. Revenue up 6 figures. In 7 days. No guessing.
> After: The launch generated six-figure revenue in 7 days.

**29. Aphorism formulas**
Patterns to cut: "X is the Y of Z", "X becomes a trap", "X is not a tool but a mirror", "the language of", "the currency of"
Fix: say the concrete claim the aphorism is gesturing at.

**30. Fake-candid openers**
Phrases to cut: Honestly?, Look, Here's the thing, The thing is, Real talk (as standalone hooks)
Fix: just say the thing.

---

## Voice Notes (Nathália-specific)

After removing AI patterns, check that the result sounds like a person who:
- Speaks three languages and has worked on four continents — internationalism is natural, not performed
- Is direct about numbers when she has them (22k leads, 400% fan growth, 5M monthly searches)
- Does not oversell — she states what happened and lets it land
- Has earned seniority over 16 years and doesn't need to argue for it

If the rewrite still sounds generic, it's probably because a real specific from knowledge-base.md or master-resume.md could replace a vague claim. Ask the user for it or note where a specific would help.

---

TEXT TO HUMANIZE:
$ARGUMENTS

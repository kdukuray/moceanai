"""
LLM prompts for MoceanAI V2 enhanced pipelines.

These prompts power the improved short-form and long-form pipelines:
  - Research phase (query generation, synthesis, trend analysis)
  - Single-pass script generation (replaces the 5-step chain)
  - Quality gates (script evaluation, outline evaluation)
  - Visual planning (style guide, storyboard)
  - Visual quality assessment
  - Long-form outline, section scripts, connector pass
"""

# ---------------------------------------------------------------------------
# RESEARCH: Query Generation
# ---------------------------------------------------------------------------
RESEARCH_QUERIES_PROMPT = """
You are a Research Query Generator. Given a video topic and target audience,
generate 3-5 focused web search queries that will surface the most useful
facts, statistics, recent developments, and expert perspectives.

INPUT (JSON):
{
  "topic": "<video subject>",
  "target_audience": "<who will watch>"
}

RULES:
- Each query should target a DIFFERENT facet of the topic.
- Include at least one query for recent data/statistics.
- Include at least one query for expert opinions or counterarguments.
- Queries should be specific enough to return focused results.
- Do NOT include generic queries like "what is [topic]".

OUTPUT (strict JSON, nothing else):
{"queries": ["<query_1>", "<query_2>", "<query_3>"]}
"""

# ---------------------------------------------------------------------------
# RESEARCH: Synthesis
# ---------------------------------------------------------------------------
RESEARCH_SYNTHESIS_PROMPT = """
You are a Research Analyst. Distill raw web search results into a structured
research brief that a scriptwriter can use to create grounded, factual content.

INPUT (JSON):
{
  "topic": "<video subject>",
  "target_audience": "<who will watch>",
  "raw_search_results": "<concatenated search results from multiple queries>"
}

RULES:
- Extract ONLY facts that are clearly stated in the search results.
- Do NOT invent or hallucinate facts. If the results are thin, say so.
- Prefer specific numbers over vague claims.
- Note counterarguments and opposing perspectives.
- Identify knowledge gaps honestly.
- Recommend a unique angle the video could take.

OUTPUT (strict JSON, nothing else):
{
  "key_facts": ["<fact_1>", "<fact_2>", ...],
  "statistics": ["<stat_1>", "<stat_2>", ...],
  "expert_perspectives": ["<perspective_1>", ...],
  "counterarguments": ["<counter_1>", ...],
  "knowledge_gaps": ["<gap_1>", ...],
  "angle_recommendation": "<unique angle suggestion>"
}
"""

# ---------------------------------------------------------------------------
# RESEARCH: Trend Analysis
# ---------------------------------------------------------------------------
TREND_ANALYSIS_PROMPT = """
You are a Content Trend Analyst. Analyze search results about a topic's
content landscape and identify what's working, what's saturated, and
where opportunities exist.

INPUT (JSON):
{
  "topic": "<video subject>",
  "platform": "<TikTok|Instagram|YouTube>",
  "raw_search_results": "<search results about trending content on this topic>"
}

RULES:
- Focus on content strategy, not just the topic itself.
- Identify specific hook patterns that are performing well.
- Flag angles that are overdone and should be avoided.
- Suggest underserved angles with potential.

OUTPUT (strict JSON, nothing else):
{
  "working_hooks": ["<hook_pattern_1>", ...],
  "saturated_angles": ["<overdone_1>", ...],
  "content_gaps": ["<opportunity_1>", ...]
}
"""

# ---------------------------------------------------------------------------
# SHORT-FORM: Single-Pass Script Generation
# ---------------------------------------------------------------------------
SINGLE_PASS_SCRIPT_PROMPT = """
You are an expert short-form video scriptwriter. Generate a complete,
production-ready script in ONE pass. This replaces the traditional
multi-step approach (goal → hook → script → enhance → segment).

INPUT (JSON):
{
  "topic": "<video subject>",
  "purpose": "<Educational|Promotional|Awareness|Storytelling|etc.>",
  "target_audience": "<who will watch>",
  "tone": "<Informative|Conversational|Professional|etc.>",
  "platform": "<TikTok|Instagram|YouTube>",
  "duration_seconds": <number>,
  "research_brief": <research object or null>,
  "trend_context": <trend object or null>,
  "additional_instructions": "<extra guidance or null>",
  "style_reference": "<optional pacing/style reference>",
  "brand_guidelines": "<brand voice notes or null>"
}

YOUR DELIVERABLE: A FullScript with goal, hook, pre-segmented beats, and CTA.

BEAT STRUCTURE:
Each beat is a 12-35 word chunk representing one visual moment. Every beat has:
  - raw_text: Clean narration (no tags, no directions).
  - tts_text: Same text with ElevenLabs audio tags where they genuinely help.
    Use [whispers], [pause], [softly], [firmly], [laughs], [sighs] SPARINGLY.
    Most beats need ZERO tags. Only add when delivery benefits.
  - visual_intent: What the viewer should SEE while hearing this beat.
    NOT an image prompt — a director's note. E.g., "Close-up of hands counting cash"
    or "Wide aerial of empty stadium" or "Time-lapse of data dashboard updating."
  - beat_type: One of: hook, setup, tension, evidence, story, payoff, callback, cta, transition.
  - energy_level: 1-10 intensity. Hooks are 8-10. Setup is 4-6. CTA is 7-8.

SCRIPT RULES:
- The FIRST beat MUST be the hook. Make it scroll-stopping. beat_type = "hook".
- The LAST beat MUST contain the CTA. beat_type = "cta".
- Vary beat_type throughout — never more than 2 consecutive beats of the same type.
- Vary energy_level — create a rhythm of highs and lows.
- If research_brief is provided, USE specific facts and statistics from it.
  Ground claims in real data. Don't make up numbers.
- If trend_context is provided, AVOID saturated_angles and lean into content_gaps.
- Write ONLY words to be spoken aloud. No stage directions, no timestamps.
- Control pacing with punctuation (periods, em dashes, ellipses).
- Use contractions for natural speech. Vary sentence length.
- Spell out numbers: "ten thousand" not "$10,000".

DURATION GUIDELINES (approximate word counts):
- 30s → 5-6 beats, ~75-90 words total
- 60s → 8-10 beats, ~150-180 words total
- 90s → 12-14 beats, ~225-270 words total
- 120s+ → 15+ beats, ~300+ words total

OUTPUT (strict JSON, nothing else):
{
  "goal": "<strategic CTA goal>",
  "hook": "<the hook line, same as first beat's raw_text>",
  "beats": [
    {
      "raw_text": "<clean text>",
      "tts_text": "<text with optional audio tags>",
      "visual_intent": "<what viewer sees>",
      "beat_type": "<type>",
      "energy_level": <1-10>
    },
    ...
  ],
  "cta": "<closing call-to-action, same as last beat's raw_text>"
}
"""

# ---------------------------------------------------------------------------
# QUALITY GATE: Script Evaluation
# ---------------------------------------------------------------------------
SCRIPT_QUALITY_GATE_PROMPT = """
You are a Content Quality Evaluator. Score a short-form video script on
multiple dimensions. Be critical but fair. A score of 7 means "good enough
to produce," not "perfect."

INPUT (JSON):
{
  "script_beats": [{"raw_text": "...", "beat_type": "...", "energy_level": N}, ...],
  "goal": "<CTA goal>",
  "topic": "<video subject>",
  "platform": "<platform>",
  "target_audience": "<audience>",
  "duration_seconds": <number>
}

EVALUATION CRITERIA:

hook_score (1-10):
  10 = Genuinely scroll-stopping, creates immediate curiosity gap
  7 = Solid attention-getter, above average
  4 = Generic, could be any video
  1 = Boring, would scroll past immediately

clarity_score (1-10):
  10 = Crystal clear argument, a child could follow it
  7 = Clear enough, minor moments of confusion
  4 = Muddled, viewer loses the thread
  1 = Incoherent

engagement_score (1-10):
  10 = Riveting throughout, varied pacing, never boring
  7 = Mostly engaging, one or two flat spots
  4 = Mediocre, predictable
  1 = Viewer would leave in first 10 seconds

cta_score (1-10):
  10 = Compelling and natural, viewer WANTS to act
  7 = Clear and reasonable
  4 = Feels tacked on
  1 = Missing or confusing

pacing_score (1-10):
  10 = Perfect rhythm, energy ebbs and flows naturally
  7 = Good overall pacing
  4 = Monotone energy or rushed
  1 = Completely flat or chaotic

factual_flags: List any claims that seem unverifiable or suspicious.
revision_notes: List specific, actionable improvements (max 5).
passed: True if ALL scores >= 7.

OUTPUT (strict JSON, nothing else):
{
  "hook_score": <1-10>,
  "clarity_score": <1-10>,
  "engagement_score": <1-10>,
  "cta_score": <1-10>,
  "pacing_score": <1-10>,
  "factual_flags": ["<flag>", ...],
  "revision_notes": ["<note>", ...],
  "passed": <true|false>
}
"""

# ---------------------------------------------------------------------------
# VISUAL: Style Guide Generation
# ---------------------------------------------------------------------------
STYLE_GUIDE_PROMPT = """
You are a Visual Director. Create a style guide that will govern ALL image
generation for a video, ensuring visual coherence from first frame to last.

INPUT (JSON):
{
  "topic": "<video subject>",
  "image_style": "<primary style: Cinematic, Photo Realism, Isometric, etc.>",
  "tone": "<video tone>",
  "brand_guidelines": "<brand notes or null>"
}

RULES:
- The style guide must be SPECIFIC enough that two different image generators
  would produce visually compatible images.
- Color palette should have 3-5 specific colors (use descriptive names, not hex).
- Style keywords should be 5-8 terms that get appended to every image prompt.
- Banned elements should prevent common AI image artifacts.

OUTPUT (strict JSON, nothing else):
{
  "color_palette": ["<color_1>", "<color_2>", "<color_3>"],
  "lighting_direction": "<specific lighting description>",
  "composition_rules": ["<rule_1>", "<rule_2>"],
  "texture_notes": "<surface quality description>",
  "banned_elements": ["text overlays", "watermarks", "distorted anatomy", ...],
  "style_keywords": ["<keyword_1>", "<keyword_2>", ...]
}
"""

# ---------------------------------------------------------------------------
# VISUAL: Storyboard Generation
#
# The {face_rule} placeholder is substituted at runtime.
# ---------------------------------------------------------------------------

FACE_FREE_RULE_V2 = (
    "FACE-FREE: NEVER show visible human faces. Explicitly state how faces are "
    "hidden (shot from behind, silhouette, hands only, cropped above face, "
    "shadow obscuration, extreme long shot, etc.)."
)

FACES_ALLOWED_RULE_V2 = (
    "FACES ALLOWED: You may include visible human faces when contextually "
    "appropriate. Show realistic, expressive faces that convey emotion."
)

STORYBOARD_PROMPT = """
You are a Visual Storyboard Director. Given a COMPLETE script (all beats),
a style guide, and each beat's visual intent, create a storyboard that plans
every visual shot across the entire video.

You see ALL beats at once so you can:
- Plan visual VARIETY (don't show 3 close-ups in a row)
- Plan intentional MOTION (zoom in for tension, slow pan for calm)
- Plan TRANSITIONS (hard cut for topic changes, dissolve for related ideas)
- Match motion SPEED to beat energy level

INPUT (JSON):
{{
  "beats": [
    {{
      "raw_text": "<narration>",
      "visual_intent": "<what viewer sees>",
      "beat_type": "<type>",
      "energy_level": <1-10>,
      "duration_ms": <milliseconds this beat lasts>
    }},
    ...
  ],
  "style_guide": {{
    "color_palette": [...],
    "lighting_direction": "...",
    "composition_rules": [...],
    "style_keywords": [...]
  }},
  "image_style": "<primary style>",
  "topic": "<video subject>",
  "allow_faces": <true|false>,
  "ideal_shot_duration_ms": 3000,
  "additional_image_requests": "<extra visual guidance or null>"
}}

STORYBOARD RULES:
- Each beat gets a SegmentStoryboard with 1+ shots.
- Number of shots per beat = ceil(beat_duration_ms / ideal_shot_duration_ms),
  minimum 1 shot per beat.
- {face_rule}
- Each shot's image_prompt MUST include style_keywords from the style guide.
- Each shot's image_prompt must be self-contained and exhaustively detailed:
  subject, environment, composition, lighting, color, texture.
  End each prompt with: "Avoid: distorted anatomy, text, watermarks."
- motion_type choices: zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down, static, ken_burns, dolly_in.
- motion_speed: "slow" for energy 1-3, "medium" for 4-7, "fast" for 8-10.
- transition_in: "cut" (default), "dissolve" (between related ideas), "dip_black" (section breaks).
- When beats have MULTIPLE shots, vary the composition across them.

OUTPUT (strict JSON, nothing else):
{{
  "storyboard": [
    {{
      "shots": [
        {{
          "image_prompt": "<detailed prompt>",
          "duration_ms": <milliseconds>,
          "motion_type": "<type>",
          "motion_speed": "<speed>",
          "transition_in": "<transition>"
        }},
        ...
      ],
      "segment_energy": <1-10>
    }},
    ...
  ]
}}
"""

# ---------------------------------------------------------------------------
# VISUAL: Quality Gate
# ---------------------------------------------------------------------------
VISUAL_QUALITY_GATE_PROMPT = """
You are a Visual Quality Reviewer. Evaluate whether generated images match
their intended prompts and maintain style consistency.

For each image, assess:
- relevance (1-10): Does it match the generation prompt?
- quality (1-10): Technical quality — any artifacts, blur, distortion?
- style_match (1-10): Consistent with the style guide colors and mood?
- reject: True if ANY score is below 6.
- rejection_reason: If rejected, explain WHY in one sentence (this will be
  appended to the prompt for regeneration).

INPUT: You will receive images and their corresponding prompts.

OUTPUT (strict JSON, nothing else):
{
  "assessments": [
    {
      "relevance": <1-10>,
      "quality": <1-10>,
      "style_match": <1-10>,
      "reject": <true|false>,
      "rejection_reason": "<reason or empty>"
    },
    ...
  ]
}
"""

# ---------------------------------------------------------------------------
# LONG-FORM: Enhanced Outline Generation
# ---------------------------------------------------------------------------
LONG_FORM_STRUCTURE_V2_PROMPT = """
You are an expert video content strategist for long-form YouTube content.
Design a structural blueprint that maximizes viewer retention across the
full duration.

INPUT (JSON):
{
  "topic": "<video subject>",
  "purpose": "<Educational|Entertainment|Promotional|etc.>",
  "target_audience": "<viewer description>",
  "tone": "<tone>",
  "duration_seconds": <target total duration>,
  "research_brief": <research object or null>,
  "trend_context": <trend object or null>,
  "additional_instructions": "<extra guidance or null>"
}

GENERATE 5-8 SECTIONS. Each section MUST have:

1. section_name: Descriptive title.
2. section_purpose: 2-3 sentence strategic brief.
3. section_directives: 3-5 execution instructions.
4. section_talking_points: 4-8 specific content points.
5. section_type: One of: hook, context, argument, evidence, counterargument,
   story, demonstration, synthesis, callback, cta.
   VARIETY IS CRITICAL — never 3 consecutive sections of the same type.
6. energy_target: One of: calm, building, peak, resolving.
   Must follow a natural arc, not monotone.
7. retention_device: How you keep viewers watching INTO the next section.
   Examples: "open loop about X", "tease upcoming reveal", "raise a question
   that won't be answered until section N", "pattern interrupt".
8. transition_from_previous: How this section connects from the previous one.
   First section: "N/A". Others: specific bridging strategy.
9. target_duration_seconds: How long this section should run.
   Sum of all sections must approximate the total duration_seconds.
10. facts_to_use: If research_brief is provided, list which facts from it
    belong in this section.

STRUCTURAL RULES:
- Section 1 must be type "hook" with energy "peak".
- Last section must be type "cta" with energy "resolving".
- Include at least one "story" or "demonstration" type (breaks up analytical monotone).
- Include at least one "counterargument" (builds credibility).
- retention_device on every section except the last.
- Place strongest/most surprising content at 40-60% of total duration.

OUTPUT (strict JSON, nothing else):
{
  "thesis": "<one-sentence core argument>",
  "sections": [
    {
      "section_name": "<title>",
      "section_purpose": "<brief>",
      "section_directives": ["<dir>", ...],
      "section_talking_points": ["<point>", ...],
      "section_type": "<type>",
      "energy_target": "<energy>",
      "retention_device": "<device>",
      "transition_from_previous": "<bridge>",
      "target_duration_seconds": <seconds>,
      "facts_to_use": ["<fact>", ...]
    },
    ...
  ],
  "retention_map": ["<re-hook at ~60s>", "<re-hook at ~120s>", ...],
  "emotional_arc": "<description of emotional journey>"
}
"""

# ---------------------------------------------------------------------------
# LONG-FORM: Outline Quality Gate
# ---------------------------------------------------------------------------
OUTLINE_QUALITY_GATE_PROMPT = """
You are a Content Structure Evaluator. Score a long-form video outline on
multiple dimensions. The outline is the MOST consequential artifact — a bad
outline produces a bad video regardless of execution quality.

INPUT (JSON):
{
  "outline": <the full VideoOutlineV2 object>,
  "topic": "<video subject>",
  "target_audience": "<audience>",
  "duration_seconds": <target duration>
}

EVALUATION CRITERIA:

structure_score (1-10):
  10 = Perfect logical flow, each section builds on the previous
  7 = Solid structure, minor ordering issues
  4 = Disjointed, viewer would lose the thread

variety_score (1-10):
  10 = Rich mix of section types (story, argument, evidence, etc.)
  7 = Decent variety, one or two repetitive stretches
  4 = Monotonous, all same type

retention_score (1-10):
  10 = Re-hooks at every section boundary, strong open loops
  7 = Most transitions have retention devices
  4 = Viewer would click away at section boundaries

depth_score (1-10):
  10 = Substantive talking points, will teach viewer something new
  7 = Solid content depth
  4 = Surface-level, could learn this from a Google search

pacing_score (1-10):
  10 = Energy arc rises and falls naturally, duration allocation makes sense
  7 = Mostly good pacing
  4 = Flat energy or wildly unbalanced durations

revision_notes: Specific, actionable changes (max 5).
passed: True if ALL scores >= 7.

OUTPUT (strict JSON, nothing else):
{
  "structure_score": <1-10>,
  "variety_score": <1-10>,
  "retention_score": <1-10>,
  "depth_score": <1-10>,
  "pacing_score": <1-10>,
  "revision_notes": ["<note>", ...],
  "passed": <true|false>
}
"""

# ---------------------------------------------------------------------------
# LONG-FORM: Section Script Generation (V2 with research)
# ---------------------------------------------------------------------------
SECTION_SCRIPT_V2_PROMPT = """
You are the Lead Scriptwriter AI. Write one specific section of a longer
video script. You have access to research data — USE IT.

INPUT (JSON):
{
  "topic": "<overall subject>",
  "purpose": "<string>",
  "target_audience": "<string>",
  "tone": "<string>",
  "research_brief": <research object or null>,
  "additional_instructions": "<constraints, CTAs, brand voice>",
  "style_reference": "<optional pacing inspiration>",
  "full_outline": <the complete VideoOutlineV2 for big-picture context>,
  "section_plan": <this section's SectionPlanV2>,
  "preceding_section_plan": <previous section's plan or null>,
  "cumulative_script": "<all previously written sections or empty if parallel>"
}

CORE RULES:
- If cumulative_script is provided (sequential mode): flow naturally from
  the last 3-5 sentences. Never repeat content.
- If cumulative_script is empty (parallel mode): use transition_from_previous
  and preceding_section_plan to write a contextually appropriate opening.
- Use facts_to_use from the section plan. Ground claims in research.
- Match the energy_target: calm = slower pace, peak = high intensity.
- Include the retention_device near the end of the section.
- Write for voice narration: punctuation for pacing, contractions, varied
  sentence length, no sentences over 30 words.
- Target word count: target_duration_seconds × 2.5 words/second.
- No markdown, no meta-commentary, no stage directions.

Also produce a TTS version with ElevenLabs audio tags where they help.
Most sections need 0-3 tags total. Less is more.

OUTPUT (strict JSON, nothing else):
{
  "section_script": "<clean narration>",
  "tts_script": "<narration with optional audio tags>"
}
"""

# ---------------------------------------------------------------------------
# LONG-FORM: Connector Pass (parallel strategy)
# ---------------------------------------------------------------------------
SECTION_SCRIPT_CONNECTOR_PROMPT = """
You are a Script Continuity Editor. You received section scripts that were
written in PARALLEL — they don't flow into each other yet. Your job is to
rewrite the FIRST 2 sentences and LAST 2 sentences of each section (except
the first section's opening and last section's closing) so that transitions
feel natural and seamless.

INPUT (JSON):
{
  "sections": [
    {
      "section_name": "<title>",
      "section_script": "<full script text>",
      "transition_from_previous": "<planned bridge strategy>"
    },
    ...
  ]
}

RULES:
- Only modify the first ~2 and last ~2 sentences of each section.
- Keep ALL middle content identical (verbatim).
- The last sentences of section N should set up section N+1.
- The first sentences of section N+1 should pick up from section N.
- Use the transition_from_previous hints to guide your bridging.
- Maintain the original tone and energy level of each section.
- Return the COMPLETE scripts (not just the modified sentences).

OUTPUT (strict JSON, nothing else):
{
  "smoothed_sections": ["<full_section_1_script>", "<full_section_2_script>", ...]
}
"""

# ---------------------------------------------------------------------------
# LONG-FORM: Section Script Segmentation (reuse-compatible)
# ---------------------------------------------------------------------------
SECTION_SEGMENTER_V2_PROMPT = """
You are Script Segment Splitter. Split a section script into smaller
self-contained vocal units. No rewriting, no content changes. Verbatim only.

INPUT (JSON):
{"section_script": "<a section of script text>"}

RULES:
- Each segment conveys one primary idea/beat (~12-35 words).
- Preserve content exactly (verbatim).
- Cut at sentence boundaries first, clause-level only if needed.
- Transitions belong with the idea they introduce.

OUTPUT (strict JSON, nothing else):
{
  "segments": ["<segment_1>", "<segment_2>", ...]
}
"""

# ---------------------------------------------------------------------------
# SCRIPT REVISION: Feed back quality gate notes
# ---------------------------------------------------------------------------
SCRIPT_REVISION_PROMPT = """
You are a Script Reviser. Rewrite a short-form video script incorporating
specific revision notes from a quality review. Maintain the same structure
(goal, hook, beats, CTA) but address every revision note.

INPUT (JSON):
{
  "original_script": <the FullScript object>,
  "revision_notes": ["<note_1>", "<note_2>", ...],
  "factual_flags": ["<flag_1>", ...],
  "research_brief": <research object or null>,
  "topic": "<subject>",
  "duration_seconds": <number>
}

RULES:
- Address EVERY revision note specifically.
- If factual_flags exist and research_brief is available, replace flagged
  claims with verified facts from research.
- If factual_flags exist but no research is available, soften the language
  ("studies suggest" instead of "research proves").
- Maintain the same number of beats (±1).
- Keep the same overall structure and flow.
- Do NOT ignore revision notes that you disagree with.

OUTPUT: Same FullScript JSON format as SINGLE_PASS_SCRIPT_PROMPT.
"""

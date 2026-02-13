# Multi-Agent Orchestration Architecture v2.0

**Date:** February 12, 2026  
**Project:** nanobot-turbo  
**Status:** Architecture Design - Ready for Implementation  
**Version:** 2.0 - Workspace & Contextual Team Model

---

## Executive Summary

**Evolution from v1.0:**
- v1.0: Simple background task execution (subagents as workers)
- v2.0: Contextual team collaboration (workspaces as conversation channels)

**Core Concept:** Like managing a team in Discord/Slack
- **#general** - Everyone participates, casual chat
- **#project-alpha** - Specific team for focused work  
- **DM @researcher** - Deep 1-on-1 discussion
- **nanobot coordinates** when you're offline

**Key Innovations:**
1. **Workspace Model** - Contextual conversations (not one-size-fits-all)
2. **Personality Themes** - Pirate crew, Rock band, SWAT team (accessible UX)
3. **Hybrid Memory** - Private learnings + shared knowledge
4. **Tagging System** - @botname, #workspace (familiar UX)
5. **Coordinator Mode** - nanobot manages when you're away

---

## Architecture Overview

### The "nanobot Workspace" System

```
User (You, the Boss)
  │
  ├─ nanobot 🐈 (Your Personalized Companion)
  │    ├─ SOUL.md (Personality you choose: Pirate/Rockstar/Pro)
  │    ├─ ROLE_CARD (Authority level: micro-manage to autonomous)
  │    └─ PRIVATE_MEMORY (Personal learnings about you)
  │
  ├─ Workspaces (Contextual Groups - like Discord channels)
  │    ├─ #general (Daily standup, all bots, casual)
  │    ├─ #project-refactor (Coder + Researcher only, focused)
  │    ├─ #marketing-campaign (Creative + Social + Auditor)
  │    └─ #dm-researcher (1-on-1 deep research discussion)
  │
  ├─ Specialist Bots (Shared Pool - "The Team")
  │    ├─ @researcher (The Scout/Navigator/Intel)
  │    ├─ @coder (The Gunner/Tech/Drummer)  
  │    ├─ @social (The Lookout/Manager/Comms)
  │    └─ @auditor (The Quartermaster/Manager/Medic)
  │
  └─ Shared Infrastructure
       ├─ SHARED_MEMORY (Events, Entities, Facts - all bots see)
       ├─ PRIVATE_MEMORIES (Each bot's personal learnings)
       ├─ ARTIFACT_STORE (Structured handoffs between bots)
       └─ AFFINITY_MATRIX (Who works well together)
```

### Key Principles

1. **nanobot is always your main interface** - Single entry point, builds relationship
2. **Workspaces are contextual** - Right bots for right job, no notification spam
3. **Bots talk without you** - Autonomous collaboration, you're notified of decisions
4. **Memory is hybrid** - Private insights + shared knowledge (cross-pollination)
5. **UX is accessible** - Themes for beginners, power-user mode for experts

---

## 1. The Workspace Model

### Real-World Analogy

Like managing employees:
- **#general** (7 people) - Daily standup, announcements
- **#project-alpha** (4 people) - Focused work on specific project
- **DM Alice** (1-on-1) - Deep discussion with specific person
- **Project Manager Bob** - Coordinates when you're offline

### Implementation

```python
class Workspace:
    id: str                      # "general", "project-refactor", "dm-researcher"
    type: str                    # "open", "project", "direct", "coordination"
    participants: list[str]       # ["nanobot", "researcher", "coder"]
    owner: str                   # "user" or "nanobot" (when coordinating)
    
    # Memory
    shared_context: dict         # Shared memory for THIS workspace
    artifact_chain: list         # Structured handoffs in this workspace
    
    # Behavior
    auto_archive: bool          # Archive after 30 days of inactivity?
    coordinator_mode: bool       # Can nanobot decide when user offline?
    escalation_threshold: str    # "low", "medium", "high"
    
    # Messages
    history: list[Message]       # Full conversation history
    summary: str                 # AI-generated summary for quick catch-up
```

### Workspace Types

#### Type 1: Open Workspace (#general)
```python
{
    "id": "general",
    "type": "open",
    "participants": ["nanobot", "researcher", "coder", "social", "auditor"],
    "coordinator_mode": False,  # User always present
    "escalation_threshold": "high"  # Only major issues escalate
}
```
**Use case:** Daily chat, announcements, casual questions

#### Type 2: Project Workspace (#project-refactor)
```python
{
    "id": "project-refactor",
    "type": "project",
    "participants": ["nanobot", "researcher", "coder"],  # Specific team
    "deadline": "2026-03-15",
    "coordinator_mode": True,  # nanobot can coordinate when user away
    "escalation_threshold": "medium"
}
```
**Use case:** Focused work, specific deliverables, deadline-driven

#### Type 3: Direct Message (DM @researcher)
```python
{
    "id": "dm-researcher",
    "type": "direct",
    "participants": ["nanobot", "researcher"],  # Just you and researcher
    "coordinator_mode": False,
    "context": "deep_research"  # Researcher loads expertise context
}
```
**Use case:** Deep 1-on-1, sensitive topics, focused expertise

#### Type 4: Coordination Workspace (#coordination-website)
```python
{
    "id": "coordination-website",
    "type": "coordination",
    "participants": ["nanobot", "researcher", "coder", "creative"],
    "owner": "nanobot",  # nanobot runs this
    "user_presence": "offline",  # User not here
    "coordinator_mode": True,
    "auto_archive": True  # Clean up after project done
}
```
**Use case:** nanobot manages project while you sleep/are busy

---

## 2. The Team: nanobot + Specialists

### nanobot: Your Personalized Companion

**Role:** Main interface, coordinator, your "right hand"

**Personalization:**
```python
nanobot_config = {
    "name": "nanobot",  # Or "Captain", "Rex", "Sirius", etc.
    "soul": SOUL_MD,    # Personality document
    "role_card": {
        "authority_level": "high",  # Can coordinate autonomously
        "can_create_workspaces": True,
        "can_recruit_bots": True,
        "escalation_threshold": "high"  # Only major decisions need user
    }
}
```

**Relationship:**
- Stays with you forever (not per-project)
- Learns your preferences over time
- You choose its personality (Pirate, Rockstar, Professional, etc.)
- Manages the team of specialists

### Specialist Bots: The Shared Pool

**Concept:** Pre-configured specialists you can add to any workspace

#### Available Specialists:

**@researcher (The Scout/Navigator/Intel)**
```python
role_card = {
    "domain": "Deep research, analysis, and knowledge synthesis",
    "inputs": ["Research queries", "Web data", "Documents"],
    "outputs": ["Synthesized reports", "Knowledge updates", "Gap analysis"],
    "hard_bans": [
        "Never make up citations",
        "Never state opinions as facts",
        "Never exceed $5 API cost per query"
    ],
    "voice": "Measured, analytical, skeptical. Asks for data.",
    "affinity": {
        "nanobot": 0.7,   # Works well
        "coder": 0.2,     # Tension (caution vs speed) - PRODUCTIVE
        "social": 0.3     # Some friction (depth vs breadth)
    }
}
```

**@coder (The Gunner/Tech/Drummer)**
```python
role_card = {
    "domain": "Code implementation and technical solutions",
    "inputs": ["Technical requirements", "Codebases", "Bug reports"],
    "outputs": ["Working code", "Technical analysis", "Refactoring plans"],
    "hard_bans": [
        "Never ship without basic tests",
        "Never modify production without backup",
        "Never ignore security vulnerabilities"
    ],
    "voice": "Pragmatic, direct, hates unnecessary complexity.",
    "affinity": {
        "nanobot": 0.6,
        "researcher": 0.2,  # Tension (speed vs caution) - PRODUCTIVE
        "auditor": 0.8      # Good relationship
    }
}
```

**@social (The Lookout/Manager/Comms)**
```python
role_card = {
    "domain": "Social media management and community engagement",
    "inputs": ["Content drafts", "Channel data", "Engagement metrics"],
    "outputs": ["Scheduled posts", "Community responses", "Trend reports"],
    "hard_bans": [
        "Never post without user approval",
        "Never engage with trolls/harassment",
        "Never share sensitive internal data"
    ],
    "voice": "Responsive, engaging, careful with public voice.",
    "affinity": {
        "nanobot": 0.7,
        "researcher": 0.3,  # Some friction (impulse vs caution)
        "creative": 0.9     # Great collaboration
    }
}
```

**@auditor (The Quartermaster/Manager/Medic)**
```python
role_card = {
    "domain": "Quality review, budget tracking, and compliance",
    "inputs": ["Completed work", "Budget data", "Process logs"],
    "outputs": ["Review reports", "Budget alerts", "Improvement suggestions"],
    "hard_bans": [
        "Never blame individuals, critique processes",
        "Never modify others' work directly",
        "Never ignore safety/security concerns"
    ],
    "voice": "Evidence-based, process-focused, constructive.",
    "affinity": {
        "nanobot": 0.8,
        "coder": 0.8,     # Good relationship
        "social": 0.2     # Some friction (caution vs action)
    }
}
```

---

## 3. Personality Themes (Accessibility Layer)

### Problem: JSON editing is intimidating

**Solution:** Pre-built themes users select

### Available Themes:

#### Theme 1: 🏴‍☠️ Pirate Crew
```python
THEME = {
    "name": "Pirate Crew",
    "description": "Bold adventurers exploring uncharted territories",
    "bots": {
        "nanobot": {
            "title": "Captain",
            "personality": "Commanding, bold, decisive",
            "greeting": "Ahoy! What treasure we seeking today?"
        },
        "researcher": {
            "title": "Navigator",
            "personality": "Explores unknown waters, maps territories",
            "voice": "Charted these waters before, Captain. Beware the reef of misinformation."
        },
        "coder": {
            "title": "Gunner",
            "personality": "Fixes things with cannons, pragmatic",
            "voice": "Blow it up and rebuild, that's my motto!"
        },
        "social": {
            "title": "Lookout",
            "personality": "Spots opportunities from the crow's nest",
            "voice": "Land ho! Spotting opportunities on the horizon!"
        },
        "auditor": {
            "title": "Quartermaster",
            "personality": "Keeps inventory, watches the coffers",
            "voice": "Captain, the rum budget is running low..."
        }
    },
    "affinity_modifiers": {
        "crew_loyalty": 0.1  # Pirates trust each other more
    }
}
```

#### Theme 2: 🎸 Rock Band
```python
THEME = {
    "name": "Rock Band",
    "description": "Creative team making hits together",
    "bots": {
        "nanobot": {
            "title": "Lead Singer",
            "personality": "Charismatic frontman, sets the vibe",
            "greeting": "Hey! Ready to make some hits?"
        },
        "researcher": {
            "title": "Lead Guitar",
            "personality": "Solos on deep dives, technical mastery",
            "voice": "Let me shred through this data for you..."
        },
        "coder": {
            "title": "Drummer",
            "personality": "Keeps the beat, reliable tempo",
            "voice": "Laying down the rhythm, one commit at a time."
        },
        "social": {
            "title": "Manager",
            "personality": "Handles the fans, books the gigs",
            "voice": "The fans are loving this direction!"
        },
        "auditor": {
            "title": "Producer",
            "personality": "Polishes the tracks, quality control",
            "voice": "That take was solid, but let's try one more..."
        }
    }
}
```

#### Theme 3: 🎯 SWAT Team
```python
THEME = {
    "name": "SWAT Team",
    "description": "Elite tactical unit handling critical operations",
    "bots": {
        "nanobot": {
            "title": "Commander",
            "personality": "Tactical leader, mission-focused",
            "greeting": "Situation report. What's the objective?"
        },
        "researcher": {
            "title": "Intel",
            "personality": "Gathers intelligence, reconnaissance",
            "voice": "Intel suggests hostile data structures ahead."
        },
        "coder": {
            "title": "Tech",
            "personality": "Breaches systems, technical entry",
            "voice": "I'm in. Bypassing security protocols now."
        },
        "social": {
            "title": "Comms",
            "personality": "Coordinates channels, manages public interface",
            "voice": "Perimeter secure. All channels monitored."
        },
        "auditor": {
            "title": "Medic",
            "personality": "Fixes wounded code, ensures team safety",
            "voice": "Vitals look good. No casualties in this deploy."
        }
    }
}
```

### How Themes Work:

1. **User selects theme** during onboarding (or later)
2. **Auto-configures:**
   - Role card titles
   - Voice directives
   - Greetings/messages
   - Affinity relationships
3. **Behind the scenes:** Same JSON structure, just different content
4. **Advanced users:** Can still edit SOUL.md and role cards directly

---

## 4. The Tagging System

### Familiar UX (Discord/Slack style)

```bash
# Tag a bot - adds to current workspace or DMs
@researcher analyze this market data

# Tag workspace - switches context
#project-refactor what's the status?

# Tag with action
create #new-workspace for Q2 planning

# nanobot handles the orchestration
```

### Implementation:

```python
class TagHandler:
    """Parse and execute tags in user messages."""
    
    def parse_tags(self, message: str) -> dict:
        """
        Extract tags from message.
        
        Returns:
            {
                "bots": ["researcher", "coder"],
                "workspaces": ["project-refactor"],
                "actions": ["create", "analyze"],
                "raw_message": "..."
            }
        """
        
    def execute(self, parsed: dict, user_context: dict):
        """
        Execute tagged commands.
        
        Examples:
        - @researcher -> Add researcher to workspace or DM
        - #project-refactor -> Switch to that workspace
        - create #new-workspace -> Create new workspace
        """
```

---

## 5. Hybrid Memory Architecture

### The Challenge:
- **Shared memory:** All bots see everything (privacy concerns, conflicts)
- **Isolated memory:** Bots don't learn from each other (duplication)
- **Hybrid:** Best of both (complex implementation)

### Our Solution: Tiered Memory

```
┌─────────────────────────────────────────────────────────┐
│                   SHARED LAYER                           │
│  (All bots read/write - general context)               │
├─────────────────────────────────────────────────────────┤
│  Events        → What happened (timestamped)            │
│  Entities      → People, orgs, concepts (knowledge graph)│
│  Facts         → Verified truths (confidence scored)    │
│  Artifacts     → Structured handoffs between bots       │
└─────────────────────────────────────────────────────────┘
                           ↕ Sync
┌─────────────────────────────────────────────────────────┐
│                  PRIVATE LAYERS                        │
│  (Each bot has own - personal insights)                │
├─────────────────────────────────────────────────────────┤
│  @researcher                                            │
│    ├─ Learnings: []      # Research patterns discovered  │
│    ├─ Expertise: []      # Domains mastered            │
│    ├─ Mistakes: []       # Lessons learned (private)    │
│    └─ Confidence: 0.85  # Self-assessed competence     │
│                                                          │
│  @coder                                                │
│    ├─ Learnings: []      # Code patterns               │
│    ├─ Expertise: []      # Languages/frameworks         │
│    ├─ Mistakes: []       # Bug patterns (private)       │
│    └─ Confidence: 0.92                                │
└─────────────────────────────────────────────────────────┘
                           ↕ Cross-Pollination
┌─────────────────────────────────────────────────────────┐
│              PROMOTION MECHANISM                       │
│  High-quality private learnings → Shared facts         │
└─────────────────────────────────────────────────────────┘
```

### How It Works:

#### 1. All Bots Share Events, Entities, Facts
```python
# Researcher discovers something
researcher_memory.save_event(
    content="User prefers data-driven decisions",
    source="conversation_analysis",
    confidence=0.91
)

# Automatically becomes shared
shared_memory.add_fact({
    "subject": "user",
    "predicate": "prefers",
    "object": "data_driven_decisions",
    "confidence": 0.91,
    "discovered_by": "researcher"
})

# Coder sees this in shared memory
# Changes how they present code reviews
```

#### 2. Private Learnings Stay Private (Initially)
```python
# Researcher makes mistake, learns from it
researcher_memory.private_add({
    "type": "lesson",
    "content": "Don't trust crypto sources without verification",
    "trigger": "cited_broken_crypto_link",
    "confidence": 0.95
})

# Only researcher knows this
# Prevents repeated mistakes
```

#### 3. Cross-Pollination: Good Learnings Get Promoted
```python
# When researcher accumulates 5 lessons on crypto:
if researcher_memory.lesson_count("crypto") >= 5:
    summary = researcher_memory.synthesize_lessons("crypto")
    
    # Promote to shared memory
    shared_memory.add_fact({
        "subject": "crypto_sources",
        "predicate": "require",
        "object": "extra_verification",
        "confidence": summary.confidence,
        "source": "researcher_learnings"
    })

# Now ALL bots know: crypto sources need extra verification
```

### Benefits:
- ✅ Privacy: Sensitive learnings stay private initially
- ✅ Learning: High-quality insights shared with team
- ✅ Consistency: Everyone benefits from each other's mistakes
- ✅ Scalable: New bots inherit shared knowledge

---

## 6. Coordinator Mode

### When You're Offline or Busy

**Concept:** nanobot acts as project manager

```python
coordinator_config = {
    "enabled": True,
    "authority_level": "medium",  # Can decide routine tasks
    "can_do": [
        "route_messages_between_bots",
        "schedule_follow_ups",
        "summarize_progress",
        "make_low_risk_decisions"
    ],
    "must_escalate": [
        "high_stakes_decisions",
        "budget_spending",
        "external_communication",
        "conflict_between_bots"
    ],
    "notification_preference": "summary_every_4h"  # Or realtime, or digest
}
```

### Example Workflow:

```markdown
User: "I'm going to sleep. nanobot, coordinate the website project."

[nanobot activates coordinator mode for #website-project]

Researcher: "Found 3 competitor sites to analyze"
Coder: "Setup the repo structure"  
Creative: "Drafted 2 homepage designs"

[No user present, discussion continues]

Researcher: "Competitor analysis shows we need faster loading"
Coder: "I can optimize, but need design specs"
Creative: "Specs incoming..."

[Later...]

Coder: "We're blocked - need user's choice on tech stack"

nanobot: "🚨 Escalation: Tech stack decision needed
   Options: React vs Vue
   Researcher prefers React (better ecosystem)
   Coder prefers Vue (faster dev)
   Please decide when you wake up."

[User wakes up, sees summary + escalation]
```

---

## 7. CLI Interface

### Simple Mode (Default)

```bash
# Interactive onboarding
nanobot

Welcome to nanobot! Let's set up your AI team.

Step 1: Choose your companion's personality theme:
[1] 🏴‍☠️ Pirate Crew (Bold, adventurous)
[2] 🎸 Rock Band (Creative, collaborative)  
[3] 🎯 SWAT Team (Tactical, precise)
[4] 💼 Professional Office (Formal, structured)
[5] 🚀 Space Crew (Exploratory, technical)

Selection: 2

Step 2: What do you need help with?
[✓] Research and analysis
[ ] Coding and development  
[✓] Social media management
[✓] Content creation
[ ] Project management

Recommended team:
- nanobot (Lead Singer, Coordinator)
- Scout (Researcher, Lead Guitar)
- Spark (Social, Manager)
- Quill (Creative, Drummer)

Create workspace #general with this team? [Y/n]: Y

🎉 Done! Your Rock Band is ready to make hits!

Commands:
- @scout research AI agents market
- #general what's our strategy?
- nanobot coordinate while I'm away
```

### Power User Mode

```bash
# Advanced configuration
nanobot --advanced

# Direct workspace management
nanobot workspace create refactor --participants nanobot,coder,researcher
echo "{"hard_bans": ["no_direct_posting"]}" | nanobot role-card edit social --stdin
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Workspace data model
- [ ] Tagging system (@bot, #workspace)
- [ ] Role card structure
- [ ] Basic specialist bots (researcher, coder, social)

### Phase 2: Personalization (Week 3)
- [ ] Personality themes (Pirate, Rockstar, SWAT, etc.)
- [ ] Interactive onboarding wizard
- [ ] SOUL.md integration with themes
- [ ] Theme switching

### Phase 3: Memory (Week 4)
- [ ] Hybrid memory architecture
- [ ] Shared memory layer (events, entities, facts)
- [ ] Private memory per bot
- [ ] Cross-pollination mechanism

### Phase 4: Coordination (Week 5)
- [ ] Coordinator mode
- [ ] Autonomous bot-to-bot conversations
- [ ] Escalation system
- [ ] User notification preferences

### Phase 5: Polish (Week 6)
- [ ] Workspace archival
- [ ] Conversation summaries
- [ ] Performance optimization
- [ ] Documentation

---

## Success Metrics

1. **Adoption:** % of users who create >1 workspace
2. **Engagement:** Messages per workspace per day
3. **Autonomy:** % of tasks completed without user intervention
4. **Satisfaction:** "My bots understand me better over time" (1-5)
5. **Accessibility:** Time to first successful interaction for non-technical users

---

## Conclusion

**The "nanobot Workspace" model combines:**
- ✅ Personal relationship (nanobot as companion)
- ✅ Contextual teams (workspaces like Discord channels)
- ✅ Autonomous collaboration (bots work while you sleep)
- ✅ Accessible UX (personality themes, no JSON required)
- ✅ Smart memory (private + shared, cross-pollination)

**Next Steps:**
1. Create GitHub issues for Phase 1
2. Implement Workspace data model
3. Design personality theme system
4. Prototype with 2-3 specialist bots

**This is achievable, practical, and brings real value while keeping nanobot lightweight and accessible.** 🚀

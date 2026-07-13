# Alex — Project Knowledge Base

This document is a knowledge base of work and personal projects, intended as source material for a digital twin / avatar system.

---

## Work Projects

_(Projects completed as part of professional roles)_


### AI Harness Framework (2026)
 
Built a harness-agnostic framework for centrally managing the files that AI coding harnesses rely on — agents.md, skills, MCP configurations, and similar artifacts. The framework maintains a single source of truth for these files and uses symlinks to point each supported harness at that centralized location, so a single update propagates instantly across every harness in use rather than requiring manual changes in multiple places.
 
Developed for the enterprise team to enforce consistency across harness configurations and establish a repeatable process for maintaining core harness files as a team, rather than leaving each individual or harness to drift out of sync. The framework was also designed to make onboarding new harnesses straightforward, keeping the system extensible as new tools are adopted.
 
**Key contributions:**
- Designed a harness-agnostic architecture centralizing shared AI harness files (agents.md, skills, MCPs, etc.)
- Implemented a symlink-based distribution model so updates in one location propagate across all connected harnesses
- Established a consistent, repeatable process for the enterprise team to maintain core harness files
- Built the framework to make adding new harnesses quick and low-effort

---

### Agentic Standup Bot (2026)
 
Built an agentic bot that delivers the team's daily standup update live in Zoom, replacing manual status reporting with an automated, spoken briefing. The bot pulls in ServiceNow ticket status, internal tooling health, and log ingestion metrics, using MCPs to collect the underlying data and metrics needed for the update.
 
Each day, the bot generates a script from a template incorporating day-of-the-week logic, so the timeframe of data being reported adjusts appropriately (for example, covering a single day versus a full weekend on a Monday). The generated script is converted to audio via a text-to-speech model, and the bot joins the team's Zoom meeting and plays the generated audio update when triggered by a designated keyword.
 
**Key contributions:**
- Designed the end-to-end agentic pipeline: data collection, script generation, TTS conversion, and Zoom playback
- Used MCPs to pull standup-relevant data from ServiceNow, internal tooling, and log ingestion sources
- Built a script template with day-of-the-week logic to correctly scope reporting timeframes
- Implemented TTS-based audio generation and keyword-triggered playback within live Zoom meetings

---

### Internal Python SDK for the PingOne API (2025)

Built an internal Python SDK wrapping the PingOne API, creating a reusable foundation for a variety of downstream scripts and tooling. The SDK abstracted away authentication, pagination, and common request/response handling, making it faster to build new PingOne-integrated tools without repeating boilerplate API logic.

On top of this SDK, developed scripts serving two main purposes: analytics and reporting capabilities beyond what was available natively in the PingOne web application, and bulk change operations across the platform that would otherwise have required tedious manual updates through the UI.

**Key contributions:**
- Designed and built an internal Python SDK around the PingOne API
- Developed custom analytics and reporting scripts to fill gaps in native platform capabilities
- Built bulk-operation scripts to efficiently perform platform-wide changes at scale

---

### Automated Pre-Assessment Framework for the CMD Independent Security Assessment (ISA) (2024)

Designed and built an automated framework that mirrored the California Military Department's (CMD) Independent Security Assessment (ISA), giving customers a way to gauge their readiness and likely score ahead of the official CMD evaluation. The ISA itself consists of two phases — a compliance audit and a penetration test — and the framework was architected to reflect that same structure, with Splunk serving as the backbone for dashboards and reporting.

For the audit phase, built customer-facing forms allowing clients to upload supporting documentation as attestation and proof of compliance. For the pentest phase, developed automated scripts to handle the assessment wherever possible, with the exception of components that required in-person execution: a wireless penetration test and a combined physical and network penetration test conducted via an on-site office walkthrough. Results from both phases were consolidated and surfaced through Splunk dashboards hosted at a customer-accessible URL, giving clients real-time visibility into their compliance and security posture ahead of their actual CMD ISA.

**Key contributions:**
- Architected the overall framework to mirror the CMD ISA's two-phase (audit + pentest) structure
- Built document upload/attestation forms for the compliance audit phase
- Developed automated penetration testing scripts to cover scriptable assessment components
- Conducted in-person wireless and physical/network penetration testing via office walkthroughs
- Built Splunk dashboards for customer-facing reporting, giving clients a live view of their projected ISA readiness

---

### Golden Configuration Framework for Zscaler Professional Services (2023)

As part of a professional services engagement with Zscaler, developed and maintained a set of "golden" baseline configurations across Zscaler's core product suite — Zscaler Internet Access (ZIA), Zscaler Private Access (ZPA), and Zscaler Digital Experience (ZDX). These configurations encoded vendor-recommended best practices and were built for rapid, API-driven deployment into new customer environments, significantly reducing the time needed to stand up a compliant baseline.

Each golden configuration served as a starting point rather than a fixed template — once deployed via the API, configurations were further tailored to meet individual customers' specific environment requirements. This approach balanced consistency and speed (via a standardized, best-practice foundation) with the flexibility needed to accommodate real-world customer variance.

**Key contributions:**
- Developed and maintained golden/baseline configurations for ZIA, ZPA, and ZDX aligned to best practices
- Built API-driven deployment workflows to rapidly provision these configurations in new customer environments
- Customized baseline configurations on a per-customer basis to meet individual environment requirements

---

### SIEM-Agnostic Detection Engineering with Atomic Threat Coverage & Atomic Red Team (2020)

Built a library of SIEM-agnostic security detections using the [Atomic Threat Coverage](https://github.com/atc-project/atomic-threat-coverage) framework, designed for deployment across customer environments regardless of underlying SIEM platform. Complemented the detection library with a corresponding suite of validation attack simulations built on [Atomic Red Team](https://github.com/redcanaryco/atomic-red-team), enabling repeatable testing of detection logic against real adversary techniques.

The end-to-end workflow covered both detection authoring and validation: detections were mapped to specific adversary tactics and techniques, then verified by executing matched Atomic Red Team tests to confirm that alerting fired as expected once deployed. This closed-loop approach ensured detections were not just written, but proven to work in practice before being handed off to customers.

**Key contributions:**
- Authored SIEM-agnostic detection logic using the Atomic Threat Coverage framework
- Built validation test cases using Atomic Red Team to simulate real-world attack techniques
- Established a repeatable process for verifying detection efficacy prior to customer deployment

---

## Personal Projects

_(Independent, side, or hobby projects)_

### AI Digital Twin / Avatar (2026)

Built a personal AI "digital twin" served through a personal website, based on the architecture of Ed Donner's avatar project. The avatar is customized with my own professional history and experience, allowing it to represent and speak on my behalf as an interactive, AI-driven version of myself. Built with a FastAPI + OpenAI Agents SDK backend, a vanilla TypeScript/Vite frontend, and Supabase persistence, with real-time human-in-the-loop chat so I can personally join and weigh in on any conversation.

Extended the base project by adding a voice agent capability powered by a cloned version of my own voice, giving the avatar the ability to interact audibly rather than purely through text.

**Key contributions:**
- Customized an existing open-source avatar architecture (based on Ed Donner's project) with personal professional history
- Built the FastAPI + OpenAI Agents SDK backend, vanilla TS/Vite frontend, and Supabase-backed persistence, including real-time human-in-the-loop chat
- Integrated an AI voice agent using a cloned voice model to enable spoken interaction

---

### Personal Knowledge Management System (Obsidian + Claude Code) (Ongoing)

Built a personal Obsidian + Claude Code system for turning raw notes into a structured, atomic personal knowledge management (PKM) workflow: consistent frontmatter, automatic linking between related notes, and Map-of-Content organization for navigating the resulting knowledge graph.

**Key contributions:**
- Designed an atomic-note PKM structure (consistent frontmatter, auto-linking, Map-of-Content organization) in Obsidian
- Used Claude Code to automate turning raw notes into structured, linked knowledge

---

### Security Tooling & CTF Practice (Ongoing)

Ongoing security-related tooling and experimentation outside of client/employer work, plus offensive-security learning projects. Active on Hack The Box (see `CONTACT.md`) for hands-on offensive-security practice and CTFs for fun (see `PERSONAL.md`).

**Key contributions:**
- Built and experimented with personal security tooling outside of professional engagements
- Practiced offensive-security techniques through Hack The Box and CTF challenges

---

### Freelance & Personal Web Development (2015-Present)

Over the years, have designed and built websites on an ongoing informal basis — both for personal use and for friends, family, and small businesses. Work has spanned a range of site types, including personal blogs, documentation sites, and small business websites, built with Astro and deployed via Cloudflare Workers.

**Key contributions:**
- Designed and built websites across a variety of use cases: blogs, documentation sites, and small business sites
- Built sites with Astro and deployed them via Cloudflare Workers
- Served as an informal go-to web developer for personal and small business needs within my network

---

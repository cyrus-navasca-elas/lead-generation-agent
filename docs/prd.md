# Product Requirements Document (PRD)

# AI Lead Generation Agent (MVP)

## Overview

The AI Lead Generation Agent is an internal tool that autonomously discovers high-quality sales prospects for our ERP platform using ZoomInfo and other public data sources.

Given a business objective (e.g., "Find mid-sized manufacturing companies that may be outgrowing Salesforce"), the agent will:

1. Generate an intelligent search strategy.
2. Query ZoomInfo for matching companies and contacts.
3. Enrich retrieved data where appropriate.
4. Score and summarize each prospect.
5. Produce a structured Excel report and JSON export for review.

The system will **not** perform outreach or automatically create CRM records during the MVP.

---

# Goals

* Reduce manual prospect research.
* Automatically identify companies matching our Ideal Customer Profile (ICP).
* Identify relevant decision makers.
* Surface likely business pain points.
* Produce an explainable ranked list of prospects.
* Export results for manual review.

---

# Non-Goals

* Email outreach
* CRM automation
* LinkedIn scraping
* Automated follow-up
* Continuous background execution
* Predictive sales analytics

---

# User Flow

1. User provides a lead generation objective or selects a predefined ICP.
2. User starts the lead generation process.
3. The system runs in the background.
4. Upon completion, the user receives:

   * Excel report
   * JSON export
5. User reviews the generated prospects.

---

# Functional Requirements

## 1. Search Planning

### Input

* Natural language objective

Example:

> Find manufacturing companies with 50–500 employees that may be experiencing CRM scaling issues.

### Process

An LLM generates one or more structured search strategies for ZoomInfo.

Example output:

* Industries
* Employee range
* Revenue range
* Technologies
* Geographic filters
* Target job titles

---

## 2. Candidate Retrieval

Execute the generated search plan using ZoomInfo.

Retrieve:

* Company name
* Industry
* Employee count
* Revenue
* Website
* Technologies used
* Company description

Retrieve associated contacts:

* Name
* Title
* Department
* Email (if available)
* Phone (if available)

---

## 3. Enrichment

Where available, retrieve additional information such as:

* Hiring activity
* Growth indicators
* Recent news
* Funding events
* Technology changes

Primary source remains ZoomInfo.

Public sources may supplement missing information.

---

## 4. Signal Extraction

Convert retrieved information into structured business signals.

Examples:

* Uses Salesforce
* Hiring RevOps
* Hiring ERP Administrator
* Growing headcount
* Multiple locations
* Recent funding
* Digital transformation initiative

---

## 5. Lead Scoring

Generate an explainable lead score using configurable rules.

Example:

Uses Salesforce: +20

100–500 employees: +15

Manufacturing: +15

Hiring RevOps: +15

Growth >20%: +10

Multiple locations: +10

Maximum score:

100

Each score must include a breakdown explaining how it was calculated.

---

## 6. AI Prospect Summary

For each qualified company, generate:

* Why the company matches our ICP
* Likely operational pain points
* Why our ERP may be relevant
* Recommended decision makers
* Overall confidence level

Summaries should be concise (2–4 sentences).

---

## 7. Export Results

Generate:

### Excel Workbook

Sheet 1 — Companies

* Company
* Industry
* Employees
* Revenue
* Technologies
* Lead Score
* Pain Points
* AI Summary

Sheet 2 — Contacts

* Company
* Name
* Title
* Department
* Email
* Phone
* Reason to Contact

### JSON

Export complete structured data for future integration into the ERP.

---

# Technical Architecture

User

↓

Lead Generation Script / API Endpoint

↓

LLM Search Planner

↓

ZoomInfo API

↓

Signal Extraction

↓

Lead Scoring

↓

LLM Prospect Summary

↓

Excel + JSON Export

---

# Technology Stack

Language

* Python

Framework

* FastAPI (optional if exposed through ERP)

Libraries

* httpx (API requests)
* pandas (data processing)
* openpyxl (Excel generation)
* OpenAI SDK (LLM)

No database is required for the MVP.

Generated files serve as the system output.

---

# Inputs

* Lead generation objective
* Optional ICP filters
* Optional company size
* Optional geography
* Optional industry

---

# Outputs

Excel report containing:

* Ranked companies
* Decision makers
* Contact information
* Lead scores
* AI-generated summaries

JSON export containing:

* Raw retrieved data
* Structured signals
* Lead scoring breakdown
* AI insights

---

# Success Metrics

* Number of qualified companies identified.
* Number of qualified contacts identified.
* Average lead score.
* Percentage of leads accepted by sales.
* Total execution time.

---

# Risks

* Incomplete third-party data.
* API rate limits.
* False positives from AI-generated pain point inference.
* Duplicate companies across searches.

---

# Future Enhancements

* Direct CRM integration.
* Scheduled recurring searches.
* Historical lead tracking.
* User feedback to improve scoring.
* Multi-source enrichment.
* Automated deduplication.
* Configurable scoring models.
* Competitive replacement detection (Salesforce, HubSpot, Dynamics, SAP).

---

# MVP Deliverable

A user can initiate a lead search, allow the system to run unattended, and receive a ranked Excel workbook and JSON export containing qualified companies, relevant decision makers, lead scores, and AI-generated prospect summaries. No outreach or CRM automation is included in the MVP.

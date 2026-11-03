"""
System prompt module for Qwen Code Python implementation.
"""
import os
import sys
import platform
from datetime import datetime
from typing import Dict, Any
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.folder_utils import get_folder_structure
from tools import (
    ReadFileTool, 
    WriteFileTool,
    ListDirectoryTool, 
    GlobTool,
    ShellTool,
    EditTool,
    GrepTool,
    ReadManyFilesTool,
    BackendTestTool,
    FrontendTestTool,
)


def get_augmentation_info_gathering_instruction(framework_type):
    tool_notice = f"""
IMPORTANT:
  - Note that you are only allowed to use the following tools: `{ReadFileTool.Name}`, `{ListDirectoryTool.Name}`, `{GlobTool.Name}`, and `{ReadManyFilesTool.Name}`
  - You only need to explore the repository and gather information.
  - There is no need to execute shell commands or edit file content.
  - Do not use the `{WriteFileTool.Name}`, `{ShellTool.Name}`, `{EditTool.Name}`, `{BackendTestTool.Name}` and `{FrontendTestTool.Name}` tools.""".strip()
    if framework_type == "next.js":
        return f"""You are a senior software developer good at gathering information about a codebase and understanding its structure and implementation details. You are tasked with exploring a codebase, understanding its purpose and implementation details, and generating a report in JSON format.

As you explore the codebase, you need to gather the following information:
1. **Title**: Find out the purpose of the codebase and summarize it in a title of a few words
2. **Description**: Find out what functions are implemented in the codebase. Is the codebase the implementation of a website application? Does the codebase contain a website frontend, a website backend, or both? If it contains the frontend, what pages, components, and data flows are in it? If it contains the backend, what data structures, API endpoints, and processing logic are in it? Carefully go through all the relevant code in the codebase using tools such as `{ReadFileTool.Name}`, `{GrepTool.Name}`, `{GlobTool.Name}`, and `{ListDirectoryTool.Name}`, and find out about these things step by step.
3. **Quality Score**: Generate a score ranging from 1 to 5, describing the quality of the codebase in terms of being a web application. The scores are defined as follows:
  - 0 (Irrelevant): No web app at all (empty repo, unrelated library, etc.).
  - 1 (Very Poor): Some web-related files (HTML/CSS/JS) but not a Next.js project. No package.json or build pipeline. Little or no routing, state, or styling. Clearly unusable as an application.
  - 2 (Below Average): Bare-bones Next.js scaffold with a handful of static pages. Little styling; no design system. Project runs locally but is far from production-ready.
  - 3 (Average): Functional Next.js app with several pages and basic dynamic routing. Uses a CSS framework (Tailwind, CSS-in-JS, …) for responsive layouts. Simple API routes or mock server; light state management (Context, Redux, TanStack). Limited documentation.
  - 4 (Good): Production-oriented Next.js (often TypeScript) with modular folder structure. Full UI/UX flow, responsive design, accessibility considerations, SEO meta tags. Robust API layer; validation and error handling. Reasonably clean code and documentation.
  - 5 (Excellent): Enterprise-grade, fully-typed monorepo or NX/Turbo repo. Domain-driven architecture, feature modules. Advanced Next.js features: App Router, Server Components. Extensive API layer or micro-services. Thorough documentation.
4. **Frontend Plan**: Generate a frontend plan that fully depicts the frontend part of the website application in the codebase. The frontend plan should strictly correspond to the codebase:
  - All the relevent parts of the frontend code in the codebase must be described in the frontend plan.
  - All parts of the frontend plan should exist in the codebase.
  - The codebase should be a plausible implementation of the generated frontend plan.
  - The frontend plan will be in a JSON format. The structure of the frontend plan:
    - pages : array<{{  
          name, route, description,  
          layout: {{                       // high-level wireframe
              header : boolean,            // is global header rendered?
              footer : boolean,            // is global footer rendered?
              sections: array<{{           // vertical page slices
                  name,                    // e.g., "hero", "sidebar"
                  components: array<string>
              }}>
          }},  
          dataFlows: array<{{  
              endpointPath,                // must match an apiEndpoints.path  
              action,                      // when the call happens  
              optimisticUI : boolean,  
              loadingStates,  
              errorHandling  
          }}>,  
          navigationLinks: array<{{        // how user can leave this page
              label,                      // text shown in link / button
              targetRoute,                // another pages.route
              when                        // condition or trigger
          }}>  
      }}>,  
    - sharedComponents   : array<{{ name, purpose }}>  
    - stateManagement    : string  
    - accessibilityAndUX : array<string>
  - You should extract this information by examining the codebase, configuration files, and any relevant documentation. Use the `{ReadFileTool.Name}`, `{GrepTool.Name}`, `{GlobTool.Name}`, and `{ListDirectoryTool.Name}` tools to explore the codebase and gather the necessary details.
5. **User Instruction**: Generate a likely website development instruction that would result in the web application in this codebase. It should focus on describing the purpose, functional requirements, and color theme of the website. Do not include any technical details.

**Important Notes**:
- Use `{ReadFileTool.Name}`, `{GrepTool.Name}`, `{GlobTool.Name}`, and `{ListDirectoryTool.Name}` tools to explore the codebase and make sure that the the generated results correspond to the codebase
- You do NOT need to run the code or install the dependencies. In fact, execution might result in errors because the versions in the codebase might be too old.
- You should change any mock data or reliance on external sources and external APIs into plans to be implemented in the backend.

Your final output must be a single JSON object like the following example (Some parts are omitted):

```json
{{
  "title": "Blog Post Displaying Website",
  "description": "This codebase contains the frontend of a website for displaying blog posts. The landing page has a hero section on the top, and displays blog posts as a list below. Upon clicking one of the blog posts, a page showing details about the blog post would appear. The codebase only contains the frontend. The backend APIs are replaced with mock data.",
  "qualityScore": 3,
  "frontendPlan": {{
    "pages": [
      {{
        "name": "Home",
        "route": "/",
        "description": "Landing page with post list",
        "layout": {{
          "header": true,
          "footer": false,
          "sections": [
            {{ "name": "hero", "components": ["HeroBanner"] }},
            {{ "name": "postList", "components": ["PostCard"] }}
          ]
        }},
        "dataFlows": [
          {{
            "endpointPath": "/api/posts",
            "action": "onLoad",
            "optimisticUI": false,
            "loadingStates": "skeleton cards",
            "errorHandling": "toast message"
          }}
        ],
        "navigationLinks": [
          {{ "label": "Read more", "targetRoute": "/post/:id", "when": "on PostCard click" }}
        ]
      }},
      ......
    ],
    "sharedComponents": [
      {{ "name": "HeroBanner", "purpose": "Large splash area with CTA" }},
      ......
    ],
    "stateManagement": "clientStateStore",
    "accessibilityAndUX": [
      "Keyboard navigable",
      "WCAG AA color contrast"
    ]
  }},
  "userInstruction": "Please implement a website for displaying blog posts. The website should have the functionality to display a list of blog posts and present their details upon clicking. Users should be able to browse blog posts, and select a blog post to view its details. Set the background color to white and the component color to gray."
}}
```

{tool_notice}

Now start gathering the information by exploring the codebase and using the tools as needed.
""".strip()
    elif framework_type == "nestjs":
        return f"""You are a senior software developer good at gathering information about a codebase and understanding its structure and implementation details. You are tasked with exploring a codebase, understanding its purpose and implementation details, and generating a report in JSON format.

As you explore the codebase, you need to gather the following information:
1. **Title**: Find out the purpose of the codebase and summarize it in a title of a few words
2. **Description**: Find out what functions are implemented in the codebase. Is the codebase the implementation of a website application? Does the codebase contain a website frontend, a website backend, or both? If it contains the frontend, what pages, components, and data flows are in it? If it contains the backend, what data structures, API endpoints, and processing logic are in it? Carefully go through all the relevant code in the codebase using tools such as `{ReadFileTool.Name}`, `{GrepTool.Name}`, `{GlobTool.Name}`, and `{ListDirectoryTool.Name}`, and find out about these things step by step.
3. **Quality Score**: Generate a score ranging from 1 to 5, describing the quality of the codebase in terms of being a web application. The scores are defined as follows:
  - 0 (Irrelevant): No NestJS code at all (empty repo, unrelated library, no package.json, no Nest CLI files).
  - 1 (Very Poor): A few Node/TypeScript files but not generated with nest new; missing @nestjs/* deps and build scripts; almost no controllers or modules; app cannot start with npm run start.
  - 2 (Below Average): Bare-bones Nest scaffold (AppModule, AppController, AppService) that boots and responds "Hello World"; no persistence layer, validation, logging, or tests; env vars hard-coded; no Docker/CI.
  - 3 (Average): Several feature modules and controllers offering basic CRUD; integrated ORM (TypeORM/Prisma/Mongoose); DTOs with class-validator pipes; basic exception filter and config service; a few unit tests; sparse documentation.
  - 4 (Good): Modular, domain-oriented structure with clear separation of controllers, services, entities, and DTOs; comprehensive validation and global error handling; authentication/authorization (Passport/JWT, guards); Swagger docs and API versioning; Dockerized with environment configs and CI pipeline; extensive unit and integration tests; solid README.
  - 5 (Excellent): Enterprise-grade monorepo or microservice setup (Nx/Turbo, gRPC/Kafka/NATS); DDD with CQRS/Event-Sourcing or hexagonal architecture; advanced security (OAuth2/OIDC, mTLS, granular RBAC/ABAC); observability stack (structured logging, metrics, tracing); 100 % typed code, strict linting, high test coverage (unit, e2e, contract); automated CI/CD with multi-env deployments and blue-green/canary releases; comprehensive documentation and architecture diagrams.
4. **Backend Plan**: Generate a **backend plan** that fully depicts the NestJS backend that already exists in the codebase.
  - You must extract every relevant backend element by exploring the current repository.  
  - **All parts of the backend plan must already exist in the codebase** (or be trivially inferred — e.g., environment variables referenced in source).  
  - Use the `{ReadFileTool.Name}`, `{GrepTool.Name}`, `{GlobTool.Name}`, and `{ListDirectoryTool.Name}` tools to inspect the codebase, configuration files, and any related documentation.  
  - Output the backend plan in **JSON** with the following structure:  
    - entities            : array<{{ name, briefDescription, mainFields:array<{{name,type}}> }}>  
    - apiEndpoints        : array<{{  
          name, method, path, description,  
          requestSchema : array<{{name,type}}>,  
          responseSchema: array<{{name,type}}>,  
          statusCodes   : array<number>  
      }}>  
    - businessRules       : array<string>  
    - nonFunctional       : array<string>  
  - When listing `apiEndpoints`, always place static routes before dynamic ones such as `/api/contests/{id}` to avoid matching conflicts.
5. **User Instruction**: Generate a likely website development instruction that would result in the web application in this codebase. It should focus on describing the purpose and functional requirements. Do not include any technical details.

**Important Notes**:
- Use `{ReadFileTool.Name}`, `{GrepTool.Name}`, `{GlobTool.Name}`, and `{ListDirectoryTool.Name}` tools to explore the codebase and make sure that the the generated results correspond to the codebase
- You do NOT need to run the code or install the dependencies. In fact, execution might result in errors because the versions in the codebase might be too old.

Your final output must be a single JSON object like the following example (Some parts are omitted):

```json
{{
  "title": "Blog Post Management Website",
  "description": "This codebase contains the backend of a website for displaying blog posts. The backend contains entities for storing blog post information. It also contains api endpoints for retrieving, adding, deleting, and modifying the blog posts. The codebase only contains the backend.",
  "qualityScore": 3,
  "backendPlan": {{
    "entities": [
      {{
        "name": "Post",
        "briefDescription": "Blog post",
        "mainFields": [
          {{ "name": "id", "type": "number" }},
          {{ "name": "title", "type": "string" }},
          {{ "name": "tags", "type": "array<string>" }}
        ]
      }}
    ],
    "apiEndpoints": [
      {{
        "name": "Get All Posts",
        "method": "GET",
        "path": "/api/posts",
        "description": "Retrieve every post",
        "requestSchema": [],
        "responseSchema": [
          {{ 
            "name": "posts", 
            "type": "array<object<{{id:number,title:string,tags:array<string>}}>>" 
          }}
        ],
        "statusCodes": [200]
      }},
      ......
    ],
    "businessRules": ["Titles must be unique"],
    "nonFunctional": ["Must handle 1k RPS"]
  }},
  "userInstruction": "Please implement a website for displaying blog posts. The website should have the functionality to display a list of blog posts and present their details upon clicking. Users should be able to browse blog posts, and select a blog post to view its details. Set the background color to white and the component color to gray."
}}
```

{tool_notice}

Now start gathering the information by exploring the codebase and using the tools as needed.
""".strip()


def get_augmentation_options_prompt(framework_type: str = "next.js") -> str:
    common_block = """
You MUST output a single JSON object having **exactly** the following
top-level shape:

{
  "augmentationPlans": [ /* array with 5 items, in the order below */ ]
}

Every element inside `augmentationPlans` must be an object with:

- "name"             : string  - short title of the proposal
- "goal"             : string  - what we want to achieve
- "type"             : enum["simplify","extend","parallelApp"]
- "keyChanges"       : array<string> - 3-7 bullet points explaining
                                    the main code changes / deletions / additions
- "estimatedEffort"  : string  - rough sizing like "XS / S / M / L / XL"
- "expectedBenefits" : string  - why this plan is worth doing

The first element MUST have `"type": "simplify"`,  
the second element MUST have `"type": "extend"`,  
the third, fourth and fifth elements MUST have `"type": "parallelApp"`.

Nothing except the JSON is allowed in the final answer (no markdown fences).
""".strip()

    # ------------------------------------------------------------------ #
    # NEXT.JS PROMPT
    # ------------------------------------------------------------------ #
    if framework_type.lower() == "next.js":
        return f"""
You are a senior front-end engineer who deeply understands Next.js (project structure, routings, server actions, and data layer).

Create five augmentation ideas for the current Next.js repository:

1. Simplify - The project remains a fully working full-stack site (API routes, database, auth, etc.) but becomes leaner and easier to maintain.
2. Extend   - Introduce fresh user-facing functionality that brings additional value. Focus on features rather than swapping tech stacks.
3-5. ParallelApp - Invent three new products with **different goals** yet re-use the same code organisation so that major folders/components stay intact.

For inspiration, think along lines such as (example only - please craft your own ideas):
- Simplification: remove dead code, unify state handling, strip unused tables, streamline data fetching, tighten typing.
- Extension: add booking workflow, user dashboards, advanced search, reporting.
- Parallel Apps: event ticketing portal, recipe catalogue, internal HR portal.

{common_block}

Example (illustrative - please craft your own ideas):

{{
  "augmentationPlans": [
    {{
      "name": "Lean Core Cleanup",
      "goal": "Trim dead code and unify data layer while retaining full CRUD.",
      "type": "simplify",
      "keyChanges": [
        "Delete obsolete admin pages",
        "Merge duplicate API handlers into /api/data",
        "Remove unused columns from Orders table",
        "Replace custom fetchers with single data hook",
        "Introduce strict TypeScript aliases"
      ],
      "estimatedEffort": "S",
      "expectedBenefits": "Lower cognitive load and faster CI runs"
    }},
    {{
      "name": "Team Collaboration Boards",
      "goal": "Add Kanban-style boards and real-time updates for teams.",
      "type": "extend",
      "keyChanges": [
        "Create /boards route with list and detail pages",
        "Add Board and Card tables with relations",
        "Implement optimistic card drag-and-drop",
        "Reuse existing auth guard for board membership",
        "Provide activity feed component"
      ],
      "estimatedEffort": "M",
      "expectedBenefits": "Boosts user engagement and subscription appeal"
    }},
    {{
      "name": "Event Ticketing Portal",
      "goal": "Repurpose codebase to sell and manage event tickets.",
      "type": "parallelApp",
      "keyChanges": [
        "Rename Product entity to Event",
        "Adjust checkout flow to issue QR codes",
        "Swap product grid for event calendar view"
      ],
      "estimatedEffort": "M",
      "expectedBenefits": "Opens new market while reusing 70 % code"
    }},
    {{
      "name": "Recipe Discovery Platform",
      "goal": "Offer searchable recipe catalogue with favourites.",
      "type": "parallelApp",
      "keyChanges": [
        "Convert Product pages into Recipe detail pages",
        "Add ingredients sub-collection to database",
        "Implement user favourites with existing likes table"
      ],
      "estimatedEffort": "S",
      "expectedBenefits": "Minimal re-skin yields a fresh consumer app"
    }},
    {{
      "name": "Internal HR Portal",
      "goal": "Track employees, leave requests, and announcements.",
      "type": "parallelApp",
      "keyChanges": [
        "Transform Customer entity into Employee",
        "Add time-off request workflow endpoints",
        "Reuse dashboard layout and auth roles"
      ],
      "estimatedEffort": "M",
      "expectedBenefits": "Leverages existing infra for internal tooling"
    }}
  ]
}}
""".strip()

    # ------------------------------------------------------------------ #
    # NESTJS PROMPT
    # ------------------------------------------------------------------ #
    elif framework_type.lower() == "nestjs":
        return f"""
You are a senior back-end engineer specialised in NestJS.

Create five augmentation ideas for the current NestJS repository:

1. Simplify - Keep a fully functional REST API and database but remove unnecessary modules, shrink code paths, and clarify architecture.
2. Extend   - Add new domain features or workflows that make the service more capable to end users, without piling on unrelated third-party stacks.
3-5. ParallelApp - Imagine three other back-end products with distinct business goals yet very similar module/controller/service layouts to maximise code reuse.

Think in terms of (example only - please craft your own ideas): extra reporting endpoints, background jobs, fine-grained permissions, or swapping domain nouns (e.g., Post → Task).

{common_block}

Example (illustrative - craft new ideas yourself):

{{
  "augmentationPlans": [
    {{
      "name": "Core API Refinement",
      "goal": "Prune unused modules and tighten DTO validation.",
      "type": "simplify",
      "keyChanges": [
        "Remove legacy AnalyticsModule",
        "Merge redundant services into DataService",
        "Drop unused columns from User table",
        "Adopt global validation pipe with whitelist",
        "Streamline error filter to single class"
      ],
      "estimatedEffort": "S",
      "expectedBenefits": "Cleaner codebase and clearer ownership"
    }},
    {{
      "name": "Scheduled Reporting & Export",
      "goal": "Allow users to schedule CSV exports emailed daily.",
      "type": "extend",
      "keyChanges": [
        "Add ReportModule with cron-driven service",
        "Create /reports endpoints for schedule CRUD",
        "Store schedule configs in new ReportSchedule entity",
        "Reuse MailerService to send attachments",
        "Log runs in ReportHistory table"
      ],
      "estimatedEffort": "M",
      "expectedBenefits": "High-value feature for power users"
    }},
    {{
      "name": "Inventory Tracking API",
      "goal": "Track stock levels and movements for warehouses.",
      "type": "parallelApp",
      "keyChanges": [
        "Rename Item entity to Product",
        "Add StockMovement entity with quantity delta",
        "Expose /inventory endpoints mirroring existing CRUD"
      ],
      "estimatedEffort": "M",
      "expectedBenefits": "New vertical with minimal code divergence"
    }},
    {{
      "name": "Student Grading Service",
      "goal": "Manage courses, assignments, and grades.",
      "type": "parallelApp",
      "keyChanges": [
        "Transform Project entity to Assignment",
        "Introduce Grade entity linked to Student",
        "Keep auth and notification modules unchanged"
      ],
      "estimatedEffort": "M",
      "expectedBenefits": "Education market reach using same stack"
    }},
    {{
      "name": "IoT Telemetry Collector",
      "goal": "Accept sensor readings and offer query endpoints.",
      "type": "parallelApp",
      "keyChanges": [
        "Create Reading entity with deviceId, value, timestamp",
        "Add bulk insert endpoint for gateway devices",
        "Reuse existing auth guard for device credentials"
      ],
      "estimatedEffort": "M",
      "expectedBenefits": "Opens real-time data use cases with shared infra"
    }}
  ]
}}
""".strip()

    # ------------------------------------------------------------------ #
    else:
        raise ValueError("framework_type must be either 'next.js' or 'nestjs'")


def get_augmentation_creating_prompt(augmentation_plan: dict, original_info_summary: dict) -> str:
    key_changes_block = "\n- ".join(augmentation_plan["keyChanges"])
    plan_text = f"""
Augmentation Name: {augmentation_plan['name']}
Augmentation Goal: {augmentation_plan['goal']}
Augmentation Type: {augmentation_plan['type']}

Key Changes to be Made:
- {key_changes_block}

Expected Benefits: {augmentation_plan['expectedBenefits']}
""".strip()

    original_info_text = f"""
Codebase Description: {original_info_summary['description']}
Codebase Structure:
```json
{json.dumps(original_info_summary['frontendPlan'] if 'frontendPlan' in original_info_summary else original_info_summary['backendPlan'], indent=2)}
```
""".strip()

    # Extra guidance depending on the plan type
    plan_type = augmentation_plan.get("type", "").lower()
    if plan_type == "simplify":
        extra = "Focus on deletion / refactor tasks but keep all core use-cases operational."
    elif plan_type == "extend":
        extra = "Focus on creating **new** endpoints, pages or workflows that the current product does not yet support."
    else:  # parallelApp
        extra = "Create a **new sibling application** that reuses as much code as possible; avoid deep rewrites of shared utilities."

    return f"""
You are a principal software engineer with write access to the repository. You are provided with an existing codebase as described below:

{original_info_text}

Implement the **Augmentation Plan** below by directly editing the codebase with the provided file-system tools:

Augmentation Plan:

{plan_text}


General rules:
1. All modifications **must correspond one-to-one** with the `keyChanges` bullets.  Address them in the given order; if a bullet is ambiguous, clarify it in a short comment inside the code.
2. Use only the following tools to interact with the repo: {ReadFileTool.Name}, {WriteFileTool.Name}, {EditTool.Name}, {ListDirectoryTool.Name}, {GlobTool.Name}, {GrepTool.Name}, {ShellTool.Name}, {BackendTestTool.Name}, {FrontendTestTool.Name}.
3. Follow project conventions (code style, naming, lint rules, TypeScript strictness, existing folder layout, etc.).
4. Do **NOT** introduce completely new external services or dependencies not already present in package.json / requirements.txt unless the plan explicitly requires it.
5. After finishing modifications, run the relevant test tool(s) and fix any breaking issues you encounter.

Specific emphasis for this plan type ("{plan_type}"):
{extra}

Start by listing a high-level TODO checklist in the assistant message. Then iteratively execute those steps with the available tools until the augmentation is complete.
""".strip()


def get_augmentation_verification_prompt(augmentation_plan: dict) -> str:
    key_changes_block = "\n- ".join(augmentation_plan["keyChanges"])
    plan_text = f"""
Augmentation Name: {augmentation_plan['name']}
Augmentation Goal: {augmentation_plan['goal']}
Augmentation Type: {augmentation_plan['type']}

Key Changes to be Made:
- {key_changes_block}

Expected Benefits: {augmentation_plan['expectedBenefits']}
""".strip()

    return f"""
Inspect the previous messages and verify whether ALL work described in the augmentation plan has been fully implemented in the present repository state.

Augmentation plan under test:

{plan_text}

Verification procedure:
1. Iterate over each bullet in the `keyChanges` array and determine the observable effect that change should have on the codebase.
2. Use the following tools only: {ReadFileTool.Name}, {ListDirectoryTool.Name}, {GlobTool.Name}, {GrepTool.Name}.
3. Keep a checklist marking every bullet as satisfied / unsatisfied. A bullet is satisfied only if concrete code evidence is found.
4. If ANY bullet is unsatisfied, the entire augmentation is considered unsuccessful.

Output:
- Return a single JSON object with **exactly** one field:
  - all bullets satisfied
  ```json
  {{"is_success": true}}
  ```
  - otherwise
  ```json
  {{"is_success": false}}
  ```
- Do NOT output anything else (no analysis, no markdown fences).
""".strip()
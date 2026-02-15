"""
BusinessProcessAutomationAI — Multi-Agent System for Process Analysis and Optimization
"""

import os
import re
import json
from datetime import datetime
import pathlib
from dotenv import load_dotenv

# Azure AI libraries
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import ConnectedAgentTool, MessageRole, ListSortOrder
from azure.identity import DefaultAzureCredential


def clean_markdown(s: str) -> str:
    """Remove basic markdown symbols for cleaner display."""
    s = s.strip()
    s = re.sub(r'【[^】]*】', '', s)  # Remove citations
    s = re.sub(r"^[\-\*\+\s]+", "", s)  # Remove leading bullets
    s = re.sub(r"^\*\*(.+?)\*\*$", r"\1", s)  # Remove double asterisks
    s = re.sub(r"^\*(.+?)\*$", r"\1", s)  # Remove single asterisks
    return s.strip()


def run_process_advisor():
    os.system("cls" if os.name == "nt" else "clear")
    load_dotenv()

    PROJECT_ENDPOINT = os.getenv('PROJECT_ENDPOINT')
    MODEL_DEPLOYMENT = os.getenv('MODEL_DEPLOYMENT_NAME')

    if not PROJECT_ENDPOINT or not MODEL_DEPLOYMENT:
        raise RuntimeError("Set PROJECT_ENDPOINT and MODEL_DEPLOYMENT_NAME in your .env file.")

    credential = DefaultAzureCredential()
    agents_client = AgentsClient(
        endpoint=PROJECT_ENDPOINT,
        credential=credential,
    )

    try:
        with agents_client:
            # --------------------- User Input ---------------------
            print("\n📋 --- Business Process Automation Advisor --- 📋\n")
            print("Describe the business process you want to analyse (multi-line, empty line to finish):")
            process_lines = []
            while True:
                line = input()
                if line == "":
                    break
                process_lines.append(line)
            process_description = "\n".join(process_lines)

            if not process_description.strip():
                print("No process description provided. Exiting.")
                return

            custom_commands = input("\nEnter any additional instructions or 'none': ").strip() or "none"
            print("\n🔍 Analysing process...\n")

            # --------------------- Create Agents ---------------------
            # Agent 1: Process Analysis
            analysis_agent = agents_client.create_agent(
                model=MODEL_DEPLOYMENT,
                name="process_analysis_agent",
                instructions=(
                    "You are a Business Process Analysis expert. "
                    "Analyse the provided process description and extract the following four items:\n"
                    "1. Current process steps – list them in order as a numbered list.\n"
                    "2. Bottlenecks or inefficiencies – identify what slows down or disrupts the process.\n"
                    "3. Tools, systems, or resources currently involved – e.g., software, equipment, manual methods.\n"
                    "4. Missing information – what additional details would you need to fully understand the process?\n\n"
                    "Present your findings in exactly four sections with the following headings: "
                    "'Process Steps', 'Bottlenecks', 'Tools Involved', 'Missing Information'. "
                    "If any category has no items, explicitly state 'None identified' under that heading. "
                    "Do not add any extra commentary outside these sections."
                )
            )

            # Agent 2: Process Optimization Advisor
            optimizer_agent = agents_client.create_agent(
                model=MODEL_DEPLOYMENT,
                name="process_optimization_advisor",
                instructions=(
                    "You are a Process Optimization Advisor. "
                    "Based on the analysis provided, recommend improvements covering exactly four categories:\n"
                    "1. Automation opportunities – which steps could be automated and with what technology.\n"
                    "2. Elimination of redundant steps – identify steps that add no value and could be removed.\n"
                    "3. Clearer ownership – who should be responsible for each step or area.\n"
                    "4. Feasibility constraints – technical, organisational, or cost limitations to consider.\n\n"
                    "Present your recommendations in exactly four sections with the following headings: "
                    "'Automation Opportunities', 'Elimination of Redundant Steps', "
                    "'Clearer Ownership', 'Feasibility Constraints'. "
                    "If any category has no items, explicitly state 'None identified' under that heading. "
                    "Do not add any extra commentary outside these sections."
                )
            )

            # Orchestrator Agent
            t_analysis = ConnectedAgentTool(
                id=analysis_agent.id,
                name="process_analysis_agent",
                description="Analyses a business process and extracts steps, bottlenecks, tools, missing info."
            )
            t_optimizer = ConnectedAgentTool(
                id=optimizer_agent.id,
                name="process_optimization_advisor",
                description="Provides automation recommendations based on process analysis."
            )

            orchestrator = agents_client.create_agent(
                model=MODEL_DEPLOYMENT,
                name="process_orchestrator",
                instructions=(
                    "You are a Process Automation Orchestrator. "
                    "The user has already provided a process description. "
                    "Your job is to:\n"
                    "1. Call the 'process_analysis_agent' to analyse the process. It will return four sections: "
                    "'Process Steps', 'Bottlenecks', 'Tools Involved', 'Missing Information'.\n"
                    "2. Take that analysis and give it to the 'process_optimization_advisor' to generate recommendations. "
                    "It will return four sections: 'Automation Opportunities', 'Elimination of Redundant Steps', "
                    "'Clearer Ownership', 'Feasibility Constraints'.\n"
                    "3. Present the final output with two main sections: "
                    "'PROCESS ANALYSIS' and 'OPTIMIZATION RECOMMENDATIONS'. "
                    "Under 'PROCESS ANALYSIS', include the four sub-sections from the analysis agent exactly as provided. "
                    "Under 'OPTIMIZATION RECOMMENDATIONS', include the four sub-sections from the optimization advisor exactly as provided. "
                    "Do not add any additional commentary or merge sections. "
                    "If any of the required eight sub-sections are missing, you must explicitly note the deficiency and ask the user to rerun."
                ),
                tools=[t_analysis.definitions[0], t_optimizer.definitions[0]]
            )

            # --------------------- Run Orchestration ---------------------
            thread = agents_client.threads.create()

            user_message = f"Process description:\n{process_description}\n"
            if custom_commands != "none":
                user_message += f"\nAdditional instructions: {custom_commands}\n"
            user_message += "\nPlease analyse and optimise this process."

            agents_client.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=user_message
            )

            run = agents_client.runs.create_and_process(
                thread_id=thread.id,
                agent_id=orchestrator.id
            )

            if run.status == "failed":
                print("Run failed:", run.last_error)
                return

            # --------------------- Retrieve and Display Results ---------------------
            messages = agents_client.messages.list(
                thread_id=thread.id,
                order=ListSortOrder.ASCENDING
            )

            # Collect assistant's final response(s)
            assistant_texts = []
            for m in messages:
                if m.role == "assistant" and m.text_messages:
                    text = m.text_messages[-1].text.value
                    assistant_texts.append(text)
                    print(text)  # immediate display

            full_report = "\n".join(assistant_texts)

            # --------------------- Save Output ---------------------
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            out_dir = pathlib.Path("./outputs")
            out_dir.mkdir(parents=True, exist_ok=True)

            # Save raw report as Markdown
            md_path = out_dir / f"process_report_{ts}.md"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# Business Process Automation Report\n\n")
                f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"## Original Process Description\n")
                f.write(f"```\n{process_description}\n```\n\n")
                if custom_commands != "none":
                    f.write(f"**Additional Instructions:** {custom_commands}\n\n")
                f.write(f"## Full Report\n\n")
                f.write(full_report)

            # Also save as JSON with metadata
            result = {
                "timestamp": datetime.now().isoformat(),
                "process_description": process_description,
                "custom_commands": custom_commands,
                "full_report": full_report
            }
            json_path = out_dir / f"process_report_{ts}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            print(f"\n📁 Reports saved:")
            print(f"  Markdown: {md_path.resolve()}")
            print(f"  JSON: {json_path.resolve()}")

    finally:
        # Clean up agents
        print("\nCleaning up agents...")
        agents_to_clean = [
            locals().get("orchestrator"),
            locals().get("analysis_agent"),
            locals().get("optimizer_agent")
        ]
        for agent in agents_to_clean:
            if agent is not None:
                try:
                    agents_client.delete_agent(agent.id)
                except Exception as e:
                    print(f"Warning: could not delete agent {agent.id}: {e}")
        print("✅ Done.")


if __name__ == "__main__":
    run_process_advisor()
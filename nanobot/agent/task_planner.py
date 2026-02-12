"""Task planner for autonomous goal decomposition and execution planning."""

import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from nanobot.providers.base import LLMProvider
from .goal import Goal, GoalManager


@dataclass
class Task:
    """Represents an executable task derived from a goal."""
    
    description: str
    goal_id: str
    task_id: str = None
    status: str = "pending"  # pending, executing, completed, failed
    dependencies: List[str] = None  # List of task IDs that must be completed first
    estimated_complexity: int = 3  # 1-5 scale
    tools_required: List[str] = None  # List of tool names required
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.task_id is None:
            import uuid
            self.task_id = str(uuid.uuid4())
        if self.dependencies is None:
            self.dependencies = []
        if self.tools_required is None:
            self.tools_required = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ExecutionPlan:
    """Represents a complete execution plan for a goal."""
    
    tasks: List[Task]
    goal_id: str
    plan_id: str = None
    created_at: str = None
    status: str = "pending"  # pending, executing, completed, failed
    
    def __post_init__(self):
        if self.plan_id is None:
            import uuid
            self.plan_id = str(uuid.uuid4())
        if self.created_at is None:
            from datetime import datetime
            self.created_at = datetime.now().isoformat()
    
    def get_executable_tasks(self) -> List[Task]:
        """Get tasks that are ready to execute (no pending dependencies)."""
        executable = []
        completed_tasks = {task.task_id for task in self.tasks if task.status == "completed"}
        
        for task in self.tasks:
            if task.status == "pending":
                # Check if all dependencies are completed
                if all(dep_id in completed_tasks for dep_id in task.dependencies):
                    executable.append(task)
        
        return executable
    
    def is_completed(self) -> bool:
        """Check if all tasks in the plan are completed."""
        return all(task.status == "completed" for task in self.tasks)
    
    def is_failed(self) -> bool:
        """Check if any task in the plan has failed."""
        return any(task.status == "failed" for task in self.tasks)
    
    def get_progress(self) -> float:
        """Calculate overall progress of the execution plan."""
        if not self.tasks:
            return 1.0
        
        completed_count = sum(1 for task in self.tasks if task.status == "completed")
        return completed_count / len(self.tasks)


class TaskPlanner:
    """Plans and manages task execution for autonomous goal achievement."""
    
    def __init__(self, goal_manager: GoalManager, llm_provider: LLMProvider, 
                 workspace_path: str = "/root/.nanobot/workspace"):
        self.goal_manager = goal_manager
        self.llm_provider = llm_provider
        self.workspace_path = Path(workspace_path)
        self.execution_plans_file = self.workspace_path / "memory" / "execution_plans.json"
        self.execution_plans = self._load_execution_plans()
    
    def _load_execution_plans(self) -> Dict[str, ExecutionPlan]:
        """Load execution plans from file."""
        if not self.execution_plans_file.exists():
            return {}
        
        try:
            with open(self.execution_plans_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                plans = {}
                for plan_id, plan_data in data.items():
                    tasks = [Task(**task_data) for task_data in plan_data["tasks"]]
                    plan = ExecutionPlan(
                        tasks=tasks,
                        goal_id=plan_data["goal_id"],
                        plan_id=plan_id,
                        created_at=plan_data["created_at"],
                        status=plan_data["status"]
                    )
                    plans[plan_id] = plan
                return plans
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Error loading execution plans: {e}")
            return {}
    
    def _save_execution_plans(self):
        """Save execution plans to file."""
        data = {}
        for plan_id, plan in self.execution_plans.items():
            data[plan_id] = {
                "tasks": [task.__dict__ for task in plan.tasks],
                "goal_id": plan.goal_id,
                "created_at": plan.created_at,
                "status": plan.status
            }
        
        with open(self.execution_plans_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    async def decompose_goal(self, goal: Goal, model: str = None) -> List[Goal]:
        """Use LLM to decompose a goal into sub-goals."""
        prompt = f"""
You are an expert task planner. Decompose the following goal into specific, actionable sub-goals:

Main Goal: {goal.description}

Requirements:
1. Each sub-goal should be specific, measurable, and achievable
2. Sub-goals should be ordered logically (consider dependencies)
3. Include estimated complexity for each sub-goal (1-5 scale, where 1=simple, 5=complex)
4. Consider what tools or resources might be needed for each sub-goal
5. Return as JSON array with fields: description, priority, complexity

Return only valid JSON, nothing else.
"""
        
        messages = [{"role": "user", "content": prompt}]
        response = await self.llm_provider.chat(messages=messages, model=model)
        
        try:
            sub_goals_data = json.loads(response.content)
            if not isinstance(sub_goals_data, list):
                raise ValueError("Expected JSON array")
            
            sub_goals = []
            for data in sub_goals_data:
                if not isinstance(data, dict):
                    continue
                
                sub_goal = Goal(
                    description=data.get("description", ""),
                    priority=data.get("priority", 1),
                    metadata={
                        "complexity": data.get("complexity", 3),
                        "parent_goal": goal.id
                    }
                )
                sub_goals.append(sub_goal)
            
            return sub_goals
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"Error parsing LLM response for goal decomposition: {e}")
            # Fallback: create a simple sub-goal
            return [Goal(
                description=f"Complete step for: {goal.description}",
                priority=goal.priority,
                metadata={"complexity": 3, "parent_goal": goal.id}
            )]
    
    async def create_execution_plan(self, goal: Goal, model: str = None) -> ExecutionPlan:
        """Create an execution plan for a goal."""
        # If goal has no sub-goals, create a single task
        if not goal.sub_goals:
            task = Task(
                description=goal.description,
                goal_id=goal.id,
                estimated_complexity=goal.metadata.get("complexity", 3)
            )
            plan = ExecutionPlan(tasks=[task], goal_id=goal.id)
            self.execution_plans[plan.plan_id] = plan
            self._save_execution_plans()
            return plan
        
        # For goals with sub-goals, create tasks for each sub-goal
        tasks = []
        for sub_goal_id in goal.sub_goals:
            sub_goal = self.goal_manager.get_goal(sub_goal_id)
            if sub_goal:
                task = Task(
                    description=sub_goal.description,
                    goal_id=sub_goal_id,
                    estimated_complexity=sub_goal.metadata.get("complexity", 3)
                )
                tasks.append(task)
        
        # Add dependencies based on logical ordering (simple sequential for now)
        for i in range(1, len(tasks)):
            tasks[i].dependencies.append(tasks[i-1].task_id)
        
        plan = ExecutionPlan(tasks=tasks, goal_id=goal.id)
        self.execution_plans[plan.plan_id] = plan
        self._save_execution_plans()
        return plan
    
    def get_execution_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get an execution plan by ID."""
        return self.execution_plans.get(plan_id)
    
    def get_plan_for_goal(self, goal_id: str) -> Optional[ExecutionPlan]:
        """Get the execution plan for a specific goal."""
        for plan in self.execution_plans.values():
            if plan.goal_id == goal_id:
                return plan
        return None
    
    def update_task_status(self, plan_id: str, task_id: str, status: str, 
                          result: str = None) -> bool:
        """Update the status of a task in an execution plan."""
        if plan_id not in self.execution_plans:
            return False
        
        plan = self.execution_plans[plan_id]
        for task in plan.tasks:
            if task.task_id == task_id:
                task.status = status
                if result:
                    task.metadata["result"] = result
                break
        else:
            return False
        
        # Update plan status
        if plan.is_completed():
            plan.status = "completed"
        elif plan.is_failed():
            plan.status = "failed"
        else:
            plan.status = "executing"
        
        self._save_execution_plans()
        return True
    
    def get_next_tasks(self, plan_id: str) -> List[Task]:
        """Get the next set of executable tasks for a plan."""
        plan = self.get_execution_plan(plan_id)
        if not plan:
            return []
        return plan.get_executable_tasks()
    
    def get_plan_progress(self, plan_id: str) -> float:
        """Get the progress of an execution plan."""
        plan = self.get_execution_plan(plan_id)
        if not plan:
            return 0.0
        return plan.get_progress()
    
    async def suggest_optimizations(self, goal_description: str, 
                                  previous_results: List[str] = None, 
                                  model: str = None) -> Dict[str, Any]:
        """Use LLM to suggest optimizations based on previous results."""
        context = f"Goal: {goal_description}\n"
        if previous_results:
            context += "Previous attempts:\n"
            for i, result in enumerate(previous_results, 1):
                context += f"{i}. {result[:200]}...\n"
        
        prompt = f"""
Based on the following context, suggest improvements for achieving the goal:

{context}

Provide suggestions in JSON format with these fields:
- "strategy_improvements": list of strategic improvements
- "tool_recommendations": list of recommended tools or approaches  
- "potential_pitfalls": list of potential issues to avoid
- "success_metrics": list of ways to measure success

Return only valid JSON.
"""
        
        messages = [{"role": "user", "content": prompt}]
        response = await self.llm_provider.chat(messages=messages, model=model)
        
        try:
            suggestions = json.loads(response.content)
            return suggestions
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing optimization suggestions: {e}")
            return {
                "strategy_improvements": [],
                "tool_recommendations": [],
                "potential_pitfalls": [],
                "success_metrics": []
            }
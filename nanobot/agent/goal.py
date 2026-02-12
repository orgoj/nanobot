"""Goal representation and management for autonomous task planning."""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class Goal:
    """Represents a goal in the autonomous task planning system."""
    
    description: str
    priority: int = 1
    deadline: Optional[str] = None  # ISO format datetime string
    status: str = "pending"  # pending, in_progress, completed, failed
    created_at: str = None  # ISO format datetime string
    completed_at: Optional[str] = None  # ISO format datetime string
    progress: float = 0.0  # 0.0 - 1.0
    sub_goals: List[str] = None  # List of goal IDs
    dependencies: List[str] = None  # List of goal IDs that must be completed first
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.sub_goals is None:
            self.sub_goals = []
        if self.dependencies is None:
            self.dependencies = []
        if self.metadata is None:
            self.metadata = {}
        if isinstance(self.priority, str):
            self.priority = int(self.priority)
        if isinstance(self.progress, str):
            self.progress = float(self.progress)
    
    @property
    def id(self) -> str:
        """Generate a consistent ID based on the goal content."""
        # For now, use a simple hash-based approach
        # In production, we might want to use a proper UUID
        return str(uuid.uuid4())
    
    @property
    def is_completed(self) -> bool:
        """Check if the goal is completed."""
        return self.status == "completed"
    
    @property
    def is_failed(self) -> bool:
        """Check if the goal has failed."""
        return self.status == "failed"
    
    @property
    def has_deadline(self) -> bool:
        """Check if the goal has a deadline."""
        return self.deadline is not None
    
    @property
    def deadline_datetime(self) -> Optional[datetime]:
        """Get deadline as datetime object."""
        if self.deadline:
            return datetime.fromisoformat(self.deadline)
        return None
    
    @property
    def is_overdue(self) -> bool:
        """Check if the goal is overdue."""
        if self.has_deadline and not self.is_completed:
            return datetime.now() > self.deadline_datetime
        return False
    
    def update_progress(self, progress: float):
        """Update progress and ensure it's within bounds."""
        self.progress = max(0.0, min(1.0, progress))
        if self.progress >= 1.0:
            self.status = "completed"
            if self.completed_at is None:
                self.completed_at = datetime.now().isoformat()
    
    def mark_in_progress(self):
        """Mark the goal as in progress."""
        self.status = "in_progress"
    
    def mark_failed(self, reason: str = ""):
        """Mark the goal as failed."""
        self.status = "failed"
        if reason:
            self.metadata["failure_reason"] = reason
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert goal to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Goal":
        """Create goal from dictionary."""
        return cls(**data)


class GoalManager:
    """Manages goals and their lifecycle in the autonomous task planning system."""
    
    def __init__(self, workspace_path: str = "/root/.nanobot/workspace"):
        self.workspace_path = Path(workspace_path)
        self.goals_file = self.workspace_path / "memory" / "goals.json"
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        (self.workspace_path / "memory").mkdir(exist_ok=True)
        self.goals = self._load_goals()
    
    def _load_goals(self) -> Dict[str, Goal]:
        """Load goals from file."""
        if not self.goals_file.exists():
            return {}
        
        try:
            with open(self.goals_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {goal_id: Goal.from_dict(goal_data) for goal_id, goal_data in data.items()}
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Error loading goals: {e}")
            return {}
    
    def _save_goals(self):
        """Save goals to file."""
        data = {goal_id: goal.to_dict() for goal_id, goal in self.goals.items()}
        with open(self.goals_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def create_goal(self, description: str, priority: int = 1, 
                   deadline: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Goal:
        """Create a new goal and save it."""
        goal = Goal(
            description=description,
            priority=priority,
            deadline=deadline,
            metadata=metadata or {}
        )
        # Generate a proper ID and store it
        goal_id = str(uuid.uuid4())
        self.goals[goal_id] = goal
        self._save_goals()
        return goal
    
    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID."""
        return self.goals.get(goal_id)
    
    def get_all_goals(self) -> List[Goal]:
        """Get all goals."""
        return list(self.goals.values())
    
    def get_active_goals(self) -> List[Goal]:
        """Get all goals that are not completed or failed."""
        return [goal for goal in self.goals.values() if goal.status in ["pending", "in_progress"]]
    
    def get_completed_goals(self) -> List[Goal]:
        """Get all completed goals."""
        return [goal for goal in self.goals.values() if goal.status == "completed"]
    
    def get_failed_goals(self) -> List[Goal]:
        """Get all failed goals."""
        return [goal for goal in self.goals.values() if goal.status == "failed"]
    
    def update_goal(self, goal_id: str, **kwargs) -> bool:
        """Update a goal's properties."""
        if goal_id not in self.goals:
            return False
        
        goal = self.goals[goal_id]
        for key, value in kwargs.items():
            if hasattr(goal, key):
                setattr(goal, key, value)
        
        self._save_goals()
        return True
    
    def delete_goal(self, goal_id: str) -> bool:
        """Delete a goal."""
        if goal_id in self.goals:
            del self.goals[goal_id]
            self._save_goals()
            return True
        return False
    
    def add_sub_goal(self, parent_goal_id: str, sub_goal: Goal) -> str:
        """Add a sub-goal to a parent goal."""
        if parent_goal_id not in self.goals:
            raise ValueError(f"Parent goal {parent_goal_id} not found")
        
        sub_goal_id = str(uuid.uuid4())
        self.goals[sub_goal_id] = sub_goal
        self.goals[parent_goal_id].sub_goals.append(sub_goal_id)
        self._save_goals()
        return sub_goal_id
    
    def add_dependency(self, goal_id: str, dependency_id: str) -> bool:
        """Add a dependency to a goal."""
        if goal_id not in self.goals or dependency_id not in self.goals:
            return False
        
        if dependency_id not in self.goals[goal_id].dependencies:
            self.goals[goal_id].dependencies.append(dependency_id)
            self._save_goals()
            return True
        return False
    
    def can_execute_goal(self, goal_id: str) -> bool:
        """Check if a goal can be executed (all dependencies are completed)."""
        if goal_id not in self.goals:
            return False
        
        goal = self.goals[goal_id]
        if goal.status in ["completed", "failed"]:
            return False
        
        for dep_id in goal.dependencies:
            if dep_id not in self.goals or not self.goals[dep_id].is_completed:
                return False
        
        return True
    
    def calculate_progress(self, goal_id: str) -> float:
        """Calculate progress for a goal based on its sub-goals."""
        if goal_id not in self.goals:
            return 0.0
        
        goal = self.goals[goal_id]
        if not goal.sub_goals:
            # Leaf goal, return its own progress
            return goal.progress
        
        # Calculate weighted progress of sub-goals
        total_weight = len(goal.sub_goals)
        completed_weight = sum(1 for sub_id in goal.sub_goals 
                             if sub_id in self.goals and self.goals[sub_id].is_completed)
        
        return completed_weight / total_weight if total_weight > 0 else 0.0
    
    def update_goal_progress(self, goal_id: str):
        """Update a goal's progress based on its sub-goals."""
        if goal_id not in self.goals:
            return
        
        progress = self.calculate_progress(goal_id)
        self.update_goal(goal_id, progress=progress)
        
        # If all sub-goals are completed, mark as completed
        if progress >= 1.0:
            self.update_goal(goal_id, status="completed", completed_at=datetime.now().isoformat())
    
    def get_goal_tree(self, goal_id: str, depth: int = 0) -> Dict[str, Any]:
        """Get a hierarchical representation of a goal and its sub-goals."""
        if goal_id not in self.goals:
            return {}
        
        goal = self.goals[goal_id]
        result = {
            "id": goal_id,
            "description": goal.description,
            "status": goal.status,
            "progress": goal.progress,
            "priority": goal.priority,
            "depth": depth
        }
        
        if goal.sub_goals:
            result["sub_goals"] = [
                self.get_goal_tree(sub_id, depth + 1) 
                for sub_id in goal.sub_goals 
                if sub_id in self.goals
            ]
        
        return result
"""
Task Manager
"""

from dataclasses import dataclass, field
from typing import List
from uuid import uuid4


@dataclass
class Task:

    id: str

    title: str

    completed: bool = False


class TaskManager:

    def __init__(self):

        self.tasks: List[Task] = []

    def add_task(self, title: str):

        task = Task(

            id=str(uuid4()),

            title=title

        )

        self.tasks.append(task)

        return task

    def list_tasks(self):

        return self.tasks

    def complete(self, task_id: str):

        for task in self.tasks:

            if task.id == task_id:

                task.completed = True

                return True

        return False
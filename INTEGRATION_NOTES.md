## aonxi-memcollab integration

```python
# 1. After every send -- log trajectory
from memcollab import record, Trajectory, Outcome
traj = Trajectory(
    agent="ARIA",
    model_used=routing.model,
    profile_text=profile_text,
    defense_mode=pkm["defense_mode"],
    pkm_confidence=pkm["confidence"],
    awareness_score=pkm["awareness_score"],
    bypass_strategy=pkm["bypass_strategy"],
    channel="email",
    message_word_count=len(message.split()),
    outcome=Outcome.NO_REPLY,  # update when reply arrives
    vertical="vc",
)
trajectory_id = record(traj)

# 2. When reply classified -- update outcome
from memcollab import update_outcome
update_outcome(trajectory_id, Outcome.HOT, reply_text=reply, latency_hours=4.2)

# 3. Before generating -- inject shared memory
from memcollab import build_memory_injection
memory_context = build_memory_injection(pkm["defense_mode"], vertical)
system_prompt = base_prompt + memory_context
```

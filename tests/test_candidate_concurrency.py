from concurrent.futures import ThreadPoolExecutor

from content_rewards.store import Store


def test_automatic_candidate_and_job_created_atomically_once(tmp_path):
    path = tmp_path / "db.sqlite"
    Store(path)
    def candidate(index):
        store = Store(path)
        return store.create_candidate({"id": str(index), "campaign_id": "campaign", "platform": "youtube"})
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(candidate, range(12)))
    store = Store(path)
    assert sum(results) == 1
    jobs = store.list("job")
    assert len(jobs) == 1
    assert store.get("candidate", "campaign:youtube")["job_id"] == jobs[0]["id"]

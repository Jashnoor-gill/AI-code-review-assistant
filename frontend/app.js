const state = {
  current: null,
  jobs: [],
};

const currentReview = document.getElementById('current-review');
const jobsContainer = document.getElementById('jobs');
const form = document.getElementById('review-form');
const refreshBtn = document.getElementById('refresh-btn');
const approveBtn = document.getElementById('approve-btn');
const rejectBtn = document.getElementById('reject-btn');

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function renderCurrent(job) {
  if (!job) {
    currentReview.innerHTML = '<p class="muted">No review loaded.</p>';
    return;
  }

  const findings = (job.findings || [])
    .map((finding) => `
      <div class="finding">
        <strong class="severity-${finding.severity}">${finding.title}</strong>
        <div>${finding.message}</div>
        <div class="muted">${finding.category} ${finding.file_path ? ` - ${finding.file_path}:${finding.line_start || '?'}` : ''}</div>
      </div>
    `)
    .join('');

  currentReview.innerHTML = `
    <div class="card">
      <div><span class="tag">${job.state}</span> ${job.message}</div>
      <h3>${job.metadata?.title || job.job_id}</h3>
      <p class="muted">${job.metadata?.provider || 'local'} / ${job.metadata?.repository || 'local'}</p>
      <p><strong>${job.progress}%</strong> complete</p>
      <div class="finding"><pre style="white-space: pre-wrap; margin: 0">${job.markdown_comment || ''}</pre></div>
      ${findings}
    </div>
  `;
}

function renderJobs(jobs) {
  if (!jobs.length) {
    jobsContainer.innerHTML = '<div class="card muted">No saved reviews yet.</div>';
    return;
  }

  jobsContainer.innerHTML = jobs.map((job) => `
    <button class="list-item" data-job-id="${job.job_id}" style="text-align: left; width: 100%; color: inherit; background: rgba(255,255,255,0.03)">
      <div class="tag">${job.state}</div>
      <div><strong>${job.metadata?.title || job.job_id}</strong></div>
      <div class="muted">${job.metadata?.repository || 'local'} - ${job.findings.length} finding(s)</div>
    </button>
  `).join('');

  jobsContainer.querySelectorAll('[data-job-id]').forEach((button) => {
    button.addEventListener('click', async () => {
      const job = await request(`/api/jobs/${button.dataset.jobId}`);
      state.current = job;
      renderCurrent(job);
    });
  });
}

async function refresh() {
  const data = await request('/api/jobs');
  state.jobs = data.jobs;
  renderJobs(state.jobs);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  const job = await request('/api/reviews', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  state.current = job;
  renderCurrent(job);
  await refresh();
});

refreshBtn.addEventListener('click', refresh);

approveBtn.addEventListener('click', async () => {
  if (!state.current) return;
  const job = await request(`/api/jobs/${state.current.job_id}/approve`, { method: 'POST', body: '{}' });
  state.current = job;
  renderCurrent(job);
  await refresh();
});

rejectBtn.addEventListener('click', async () => {
  if (!state.current) return;
  const reason = prompt('Reason for rejection', 'Needs more work');
  if (reason === null) return;
  const job = await request(`/api/jobs/${state.current.job_id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
  state.current = job;
  renderCurrent(job);
  await refresh();
});

refresh().catch((error) => {
  currentReview.innerHTML = `<div class="card muted">${error.message}</div>`;
});

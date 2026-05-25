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
const workspaceHeader = document.querySelector('.workspace-header h2');

function showError(message) {
  currentReview.innerHTML = `
    <div class="card error-state">
      <p class="eyebrow">Run review failed</p>
      <h3>Something went wrong</h3>
      <p class="muted">${message}</p>
    </div>
  `;
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const response = await fetch(path, {
    headers,
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
    currentReview.innerHTML = `
      <div class="empty-state">
        <p class="eyebrow">Idle</p>
        <h3>No review loaded</h3>
        <p class="muted">Start with a diff or a repository reference. The review will appear here with findings, state, and the generated markdown comment.</p>
      </div>
    `;
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
    <div class="card review-card">
      <div class="review-card__topline">
        <div><span class="tag">${job.state}</span> ${job.message}</div>
        <div class="review-progress">${job.progress}% complete</div>
      </div>
      <h3>${job.metadata?.title || job.job_id}</h3>
      <p class="muted">${job.metadata?.provider || 'local'} / ${job.metadata?.repository || 'local'}</p>
      <div class="finding review-comment"><pre>${job.markdown_comment || ''}</pre></div>
      ${findings}
    </div>
  `;

  if (workspaceHeader) {
    workspaceHeader.textContent = `${state.jobs.length} reviews in queue`;
  }
}

function renderJobs(jobs) {
  if (!jobs.length) {
    jobsContainer.innerHTML = '<div class="card muted">No saved reviews yet.</div>';
    return;
  }

  jobsContainer.innerHTML = jobs.map((job) => `
    <button class="list-item" data-job-id="${job.job_id}" type="button">
      <div class="list-item__meta">
        <div class="tag">${job.state}</div>
        <div class="muted">${job.findings.length} finding(s)</div>
      </div>
      <div class="list-item__title"><strong>${job.metadata?.title || job.job_id}</strong></div>
      <div class="muted">${job.metadata?.repository || 'local'}</div>
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
  if (!state.current) {
    renderCurrent(null);
  }
  if (workspaceHeader) {
    workspaceHeader.textContent = `${state.jobs.length} reviews in queue`;
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  submitButton.textContent = 'Running...';
  try {
    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());
    const job = await request('/api/reviews', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    state.current = job;
    renderCurrent(job);
    await refresh();
  } catch (error) {
    showError(error.message || 'Unable to run review.');
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = 'Run review';
  }
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

renderCurrent(null);

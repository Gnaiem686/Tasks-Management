const EMPLOYEE_PREVIEW_LIMIT=5;
const ALERT_PREVIEW_LIMIT=4;
const TASK_PREVIEW_LIMIT=5;

const state={project:null,snapshot:null};
const $=(selector)=>document.querySelector(selector);
const make=(tag,text,className)=>{
  const node=document.createElement(tag);
  if(text!==undefined)node.textContent=text;
  if(className)node.className=className;
  return node;
};

async function readJson(path,options={}){
  const response=await fetch(path,{
    ...options,
    headers:{
      Accept:"application/json",
      ...(options.body?{"Content-Type":"application/json"}:{}),
    },
  });
  let payload;
  try{
    payload=await response.json();
  }catch{
    const error=new Error(`Request failed (${response.status}).`);
    error.status=response.status;
    error.correlationId=response.headers?.get?.("X-Correlation-ID")||null;
    throw error;
  }
  if(!response.ok){
    const detail=payload.detail;
    const message=typeof detail==="string"
      ?detail
      :detail?.message||`Request failed (${response.status}).`;
    const error=new Error(message);
    error.status=response.status;
    error.correlationId=
      detail?.correlation_id||
      payload.correlation_id||
      response.headers?.get?.("X-Correlation-ID")||
      null;
    throw error;
  }
  return payload;
}

function params(values){
  return new URLSearchParams(values).toString();
}

function formatHours(value,fallback="Unknown"){
  return value==null?fallback:`${value}h`;
}

function riskStateClass(level){
  if(["high","critical"].includes(level))return "risk-state-critical";
  if(level==="medium")return "risk-state-warning";
  if(level==="insufficient-data")return "risk-state-unknown";
  return "risk-state-good";
}

function riskChip(level,score){
  const label=level==="insufficient-data"?"Insufficient data":`${level} · ${score}/100`;
  return make("span",label,`risk-chip ${level} ${riskStateClass(level)}`);
}

function card(label,value,note){
  const node=make("article",undefined,"summary-card");
  node.append(make("small",label),make("strong",value),make("small",note));
  return node;
}

function createDrawerGroup(title,content){
  const group=make("section",undefined,"drawer-group");
  group.append(make("h3",title),content);
  return group;
}

function updateViewAll(buttonId,items,limit,title,renderer){
  const button=$(`#${buttonId}`);
  button.disabled=items.length<=limit;
  button.onclick=()=>openCollectionDrawer(title,items,renderer);
}

function openCollectionDrawer(title,items,renderer){
  $("#detail-title").textContent=title;
  const content=$("#detail-content");
  content.replaceChildren();
  if(!items.length){
    content.append(make("p","No items available."));
  }else{
    for(const item of items){
      const rendered=renderer(item);
      if(Array.isArray(rendered)){
        const group=make("section",undefined,"drawer-group");
        group.append(...rendered);
        content.append(group);
      }else{
        content.append(rendered);
      }
    }
  }
  $("#detail-drawer").showModal();
}

function openDetail(kind,item){
  $("#detail-title").textContent=kind==="employee"?item.display_name:`${item.key} · ${item.summary}`;
  const content=$("#detail-content");
  content.replaceChildren();
  for(const [key,value] of Object.entries(item)){
    if(["jira_url","score"].includes(key))continue;
    const valueNode=make(
      "p",
      Array.isArray(value)?value.join(", ")||"None":String(value??"Not available")
    );
    content.append(createDrawerGroup(key.replaceAll("_"," "),valueNode));
  }
  if(item.jira_url){
    const link=make("a","Open structured evidence in Jira");
    link.href=item.jira_url;
    link.target="_blank";
    link.rel="noopener noreferrer";
    content.append(link);
  }
  $("#detail-drawer").showModal();
}

function renderEmployeeSummary(employee){
  const workloadText=employee.remaining_hours==null
    ?"Unknown"
    :`${employee.remaining_hours}h / ${employee.capacity_hours??"?"}h`;
  return [
    make("h3",employee.display_name),
    make("p",employee.role||employee.employee_id,"muted"),
    riskChip(employee.level,employee.score??"—"),
    make("p",`Workload: ${workloadText}`),
    make("p",`Tasks: ${employee.active_tasks}`),
    make("p",`Top risk: ${employee.top_risk}`),
  ];
}

function renderAlertSummary(alert){
  return [
    riskChip(alert.severity,"!"),
    make("p",alert.subject_id,"alert-subject"),
    make("p",alert.reason),
  ];
}

function renderTaskSummary(task){
  const group=make("section",undefined,"drawer-group");
  const heading=make("h3",`${task.key} · ${task.summary}`);
  const link=make("a","Open structured evidence in Jira");
  link.href=task.jira_url;
  link.target="_blank";
  link.rel="noopener noreferrer";
  group.append(
    heading,
    make("p",`Assignee: ${task.assignee_name||"Unassigned"}`),
    make("p",`Status: ${task.status}`),
    make("p",`Due: ${task.due_date||"No due date"}`),
    make("p",`Remaining: ${formatHours(task.remaining_hours)}`),
    link
  );
  return group;
}

function renderDashboard(snapshot){
  state.snapshot=snapshot;
  const project=snapshot.project;

  $("#summary-cards").replaceChildren(
    card(
      "High-risk employees",
      String(snapshot.employees.filter((employee)=>["high","critical"].includes(employee.level)).length),
      `${snapshot.employees.length} employees`
    ),
    card(
      "At-risk tasks",
      String(project.overdue_tasks+project.blocked_tasks),
      `${project.overdue_tasks} overdue · ${project.blocked_tasks} blocked`
    ),
    card(
      "Project progress",
      `${project.completion_percent}%`,
      `${project.completed_tasks} of ${project.total_tasks} complete`
    ),
    card("Missing estimates",String(project.missing_estimate_tasks),"Structured evidence only")
  );

  $("#evidence-time").textContent=`Evidence ${new Date(snapshot.evidence_timestamp).toLocaleString()}`;

  const employeeRows=$("#employee-rows");
  employeeRows.replaceChildren();
  for(const employee of snapshot.employees.slice(0,EMPLOYEE_PREVIEW_LIMIT)){
    const row=make("tr");
    const nameCell=make("td");
    nameCell.append(
      make("strong",employee.display_name),
      make("div",employee.role||employee.employee_id,"muted")
    );
    const riskCell=make("td");
    riskCell.append(riskChip(employee.level,employee.score??"—"));
    const workloadText=employee.remaining_hours==null
      ?"Unknown"
      :`${employee.remaining_hours}h / ${employee.capacity_hours??"?"}h`;
    for(const cell of [
      nameCell,
      riskCell,
      make("td",workloadText),
      make("td",String(employee.active_tasks)),
      make("td",employee.top_risk),
    ]){
      row.append(cell);
    }
    row.tabIndex=0;
    row.addEventListener("click",()=>openDetail("employee",employee));
    row.addEventListener("keydown",(event)=>{
      if(event.key==="Enter")openDetail("employee",employee);
    });
    employeeRows.append(row);
  }

  const alertList=$("#alert-list");
  alertList.replaceChildren();
  const previewAlerts=snapshot.alerts.slice(0,ALERT_PREVIEW_LIMIT);
  if(!previewAlerts.length){
    alertList.append(make("li","No meaningful current risks."));
  }else{
    for(const alert of previewAlerts){
      const item=make("li");
      item.append(
        riskChip(alert.severity,"!"),
        make("strong",alert.subject_id,"alert-subject"),
        make("div",alert.reason,"muted")
      );
      alertList.append(item);
    }
  }

  const progress=$("#progress-content");
  progress.replaceChildren();
  progress.append(
    make("p",`${project.completed_tasks} complete · ${project.active_tasks} active`,"overview-metric"),
    make("p",`${project.due_soon_tasks} due soon · ${project.overdue_tasks} overdue`,"overview-metric"),
    make("p",`${project.blocked_tasks} blocked · ${project.missing_estimate_tasks} missing estimates`,"overview-metric")
  );
  const meter=make("div",undefined,"meter");
  const fill=make("span");
  fill.style.width=`${project.completion_percent}%`;
  meter.setAttribute("aria-label",`${project.completion_percent}% project completion`);
  meter.append(fill);
  progress.append(meter);

  const workload=$("#workload-content");
  workload.replaceChildren(
    make("p",`Overloaded: ${snapshot.workload.overloaded}`,"overview-metric"),
    make("p",`Balanced: ${snapshot.workload.balanced}`,"overview-metric"),
    make("p",`Insufficient data: ${snapshot.workload.insufficient_data}`,"overview-metric")
  );

  const taskRows=$("#task-rows");
  taskRows.replaceChildren();
  for(const task of snapshot.tasks.slice(0,TASK_PREVIEW_LIMIT)){
    const row=make("tr");
    const taskCell=make("td");
    const link=make("a",`${task.key} · ${task.summary}`);
    link.href=task.jira_url;
    link.target="_blank";
    link.rel="noopener noreferrer";
    taskCell.append(link);
    for(const cell of [
      taskCell,
      make("td",task.assignee_name||"Unassigned"),
      make("td",task.status),
      make("td",task.due_date||"No due date"),
      make("td",formatHours(task.remaining_hours)),
    ]){
      row.append(cell);
    }
    row.addEventListener("dblclick",()=>openDetail("task",task));
    taskRows.append(row);
  }

  updateViewAll(
    "view-all-employees",
    snapshot.employees,
    EMPLOYEE_PREVIEW_LIMIT,
    "All employees",
    (employee)=>renderEmployeeSummary(employee)
  );
  updateViewAll(
    "view-all-alerts",
    snapshot.alerts,
    ALERT_PREVIEW_LIMIT,
    "All alerts",
    (alert)=>renderAlertSummary(alert)
  );
  updateViewAll(
    "view-all-tasks",
    snapshot.tasks,
    TASK_PREVIEW_LIMIT,
    "All tasks",
    (task)=>renderTaskSummary(task)
  );
}

async function loadDashboard(projectKey){
  $("#page-status").textContent="Refreshing structured Jira evidence...";
  try{
    const snapshot=await readJson(`/api/v1/dashboard?${params({project_key:projectKey})}`);
    renderDashboard(snapshot);
    $("#page-status").textContent=snapshot.degraded
      ?`Partial evidence: ${snapshot.missing_sources.join(", ")}`
      :`Current project evidence loaded. Correlation: ${snapshot.correlation_id}`;
  }catch(error){
    $("#page-status").textContent=error instanceof Error?error.message:"Dashboard unavailable.";
  }
}

function historyKey(){
  return `workforce-chat:${state.project}`;
}

function assistantAvailabilityMessage(error){
  const correlation=error instanceof Error&&typeof error.correlationId==="string"
    ?error.correlationId
    :null;
  return correlation
    ?`The AI assistant is temporarily unavailable right now. Please try again in a moment. Correlation: ${correlation}`
    :"The AI assistant is temporarily unavailable right now. Please try again in a moment.";
}

function appendMessage(role,text,save=true){
  const message=make(
    "div",
    text,
    role==="user"?"user-message":role==="error"?"error-message":"assistant-message"
  );
  $("#chat-messages").append(message);
  message.scrollIntoView({block:"end"});
  if(save){
    const history=JSON.parse(sessionStorage.getItem(historyKey())||"[]");
    history.push({role,text});
    sessionStorage.setItem(historyKey(),JSON.stringify(history.slice(-20)));
  }
}

function restoreChat(){
  const panel=$("#chat-messages");
  panel.replaceChildren();
  const history=JSON.parse(sessionStorage.getItem(historyKey())||"[]");
  if(!history.length){
    appendMessage(
      "assistant",
      "Ask anything about this project's employees, tasks, deadlines, blockers, workload, or delivery risk.",
      false
    );
  }else{
    for(const message of history)appendMessage(message.role,message.text,false);
  }
}

async function sendChat(question){
  appendMessage("user",question);
  appendMessage("assistant","Investigating current project evidence...",false);
  const pending=$("#chat-messages").lastElementChild;
  try{
    const payload=await readJson(`/api/v1/investigations?${params({project_key:state.project})}`,{
      method:"POST",
      body:JSON.stringify({question,context:{project_key:state.project}}),
    });
    pending.remove();
    if(!payload.explanation||payload.explanation.source!=="bedrock"){
      throw new Error("The AI assistant could not produce a verified answer.");
    }
    if(!payload.explanation.answer){
      throw new Error("The AI assistant could not produce a verified answer.");
    }
    appendMessage("assistant",payload.explanation.answer);
  }catch(error){
    pending.remove();
    appendMessage("error",assistantAvailabilityMessage(error));
  }
}

async function loadProjects(){
  const payload=await readJson("/api/v1/projects");
  const select=$("#project-select");
  select.replaceChildren();
  for(const project of payload.items){
    const option=make("option",`${project.name} (${project.key})`);
    option.value=project.key;
    select.append(option);
  }
  const requested=new URLSearchParams(location.search).get("project");
  state.project=payload.items.some((item)=>item.key===requested)?requested:payload.items[0]?.key;
  if(!state.project)throw new Error("No project is configured.");
  select.value=state.project;
  restoreChat();
  await loadDashboard(state.project);
}

$("#project-select").addEventListener("change",async(event)=>{
  state.project=event.target.value;
  history.replaceState(null,"",`?${params({project:state.project})}`);
  restoreChat();
  await loadDashboard(state.project);
});
$("#refresh-dashboard").addEventListener("click",()=>loadDashboard(state.project));
$("#close-detail").addEventListener("click",()=>$("#detail-drawer").close());
$("#clear-chat").addEventListener("click",()=>{
  sessionStorage.removeItem(historyKey());
  restoreChat();
});
$("#chat-composer").addEventListener("submit",async(event)=>{
  event.preventDefault();
  const input=$("#manager-question");
  const question=input.value.trim();
  if(question){
    input.value="";
    await sendChat(question);
  }
});
for(const button of document.querySelectorAll("[data-question]")){
  button.addEventListener("click",()=>sendChat(button.dataset.question));
}
loadProjects().catch((error)=>{
  $("#page-status").textContent=error.message;
});

import {migrationPanel} from './migration.js';
import {focusPanel,locationCard} from './today.js';

export async function renderOnboarding(ctx) {
  const {api,esc,pageHead,state,errorMessage,navigate,aiPanel}=ctx;
  const [guide,experience]=await Promise.all([api('/api/onboarding'),api('/api/experience')]);
  if(state.view!=='onboarding')return;
  state.onboarding=guide;
  const step=guide.step,titles=['Traga seu contexto de trabalho.','IA é uma escolha sua.','Confirme o que continua em andamento.','Comece de onde você parou.'];
  const panel=document.querySelector('#content');
  panel.innerHTML=pageHead('COMEÇAR SUA MIA · '+(step+1)+' DE 4',titles[step])+
    '<ol class="journey" aria-label="Preparação"><li '+(step===0?'aria-current="step"':'')+'>Trazer contexto</li><li '+(step===1?'aria-current="step"':'')+'>IA opcional</li><li '+(step===2?'aria-current="step"':'')+'>Meu foco</li><li '+(step===3?'aria-current="step"':'')+'>Retomar</li></ol>'+ 
    '<section class="card" id="guide-body"></section><div class="actions section"><button class="btn" id="guide-back" '+(step===0?'disabled':'')+'>Voltar</button><button class="btn primary" id="guide-next">'+(step===3?'Ir para Hoje':step===1?'Continuar':'Continuar')+'</button><button class="btn ghost" id="guide-skip">Começar sem terminar a preparação</button></div>';
  const body=panel.querySelector('#guide-body');
  if(step===0){
    body.innerHTML=locationCard(experience.location,esc)+
      (experience.location?.mode==='unknown'?'<form class="form location-choice" id="location-form"><label>Onde esta instalação está rodando?<select name="mode" required><option value="">Escolha para registrar o destino dos seus arquivos</option><option value="local">Neste computador</option><option value="remote">No meu servidor</option></select></label><p class="subtle">Esta informação descreve a instalação que você já está acessando. Escolher aqui não instala, não move dados e não abre acesso remoto.</p><button class="btn" type="submit">Confirmar o destino</button><p role="status" id="location-saved"></p></form>':'')+
      '<div class="section" id="migration-panel"></div>';
    body.querySelector('#location-form')?.addEventListener('submit',async event=>{
      event.preventDefault();try{await api('/api/location',{method:'PUT',body:JSON.stringify({mode:event.currentTarget.elements.mode.value})});await renderOnboarding(ctx);}catch(error){errorMessage(error);}
    });
    await migrationPanel(body.querySelector('#migration-panel'),ctx);
  }
  if(step===1){
    body.innerHTML='<h2>Importar e buscar não precisam de modelo.</h2><p class="lede">Continue sem IA ou use um serviço compatível. APIs podem cobrar por uso; assinatura de chat e crédito de API são coisas diferentes.</p><p class="notice">Salvar a configuração não envia suas fontes e não faz uma geração. Cada pedido posterior mostra o destino e pede autorização.</p><div id="ai-panel"></div>';
    await aiPanel(body.querySelector('#ai-panel'));
  }
  if(step===2)await focusPanel(body,ctx,experience);
  if(step===3){
    const focus=experience.focus || {},library=experience.library || {};
    body.innerHTML='<p class="kicker">SUA BIBLIOTECA</p><h2>'+Number(library.active || 0)+' fontes disponíveis para usar.</h2><p class="lede">'+(focus.title?'Seu foco confirmado: '+esc(focus.title)+'.':'Você ainda pode escolher um foco em Hoje. Abra uma fonte que reconhece ou faça uma busca para começar.')+'</p><p class="subtle">'+Number(experience.migrations?.active || 0)+' importações em andamento ou aguardando revisão · '+Number(experience.migrations?.failed || 0)+' com erros. Fonte disponível não significa migração completa nem decisão vigente.</p>'+ 
      '<div class="actions"><button class="btn" id="first-search">Buscar nas minhas fontes</button><button class="btn" id="first-conversation">Começar uma conversa</button></div>'+locationCard(experience.location,esc,true);
    body.querySelector('#first-search').onclick=()=>finish('search').catch(errorMessage);
    body.querySelector('#first-conversation').onclick=()=>finish('conversations').catch(errorMessage);
  }
  if(state.view!=='onboarding' || !body.isConnected)return;
  async function save(next,completed=false){state.onboarding=await api('/api/onboarding',{method:'PUT',body:JSON.stringify({goal:guide.goal || '',expected_goal_revision:guide.goal_revision,step:next,completed})});}
  async function finish(view){await save(step,true);await ctx.refresh();navigate(view);}
  panel.querySelector('#guide-next').onclick=async()=>{try{await save(Math.min(3,step+1),step===3);await ctx.refresh();if(step===3)navigate('today');else await renderOnboarding(ctx);}catch(error){errorMessage(error);}};
  panel.querySelector('#guide-back').onclick=async()=>{try{await save(Math.max(0,step-1));await renderOnboarding(ctx);}catch(error){errorMessage(error);}};
  panel.querySelector('#guide-skip').onclick=()=>finish('today').catch(errorMessage);
}

(function(){
  "use strict";
  // Endereços antigos com # (versão de uma página só) -> páginas novas
  var h=location.hash.replace("#","");
  var mapa={exportacao:"/exportacao/",importacao:"/importacao/",paises:"/paises/",estados:"/estados/",sobre:"/sobre/"};
  if(location.pathname==="/"&&h){
    var m;
    if(mapa[h]){location.replace(mapa[h]);return;}
    if((m=h.match(/^produto-(\d{4})$/))){location.replace("/produto/"+m[1]+"/");return;}
    if((m=h.match(/^pais-(.+)$/))){location.replace("/pais/"+m[1]+"/");return;}
    if((m=h.match(/^estado-(.+)$/))){location.replace("/estado/"+m[1]+"/");return;}
  }
  // Abas (maior valor / altas / quedas)
  document.querySelectorAll("[data-tabs]").forEach(function(g){
    var bs=g.querySelectorAll("button[data-t]");
    bs.forEach(function(b){b.addEventListener("click",function(){
      bs.forEach(function(x){x.setAttribute("aria-pressed",x===b?"true":"false");});
      g.querySelectorAll("[data-p]").forEach(function(p){p.hidden=p.getAttribute("data-p")!==b.getAttribute("data-t");});
    });});
  });
  // Busca de produtos
  var busca=document.getElementById("busca");
  if(busca){
    var idx=null, out=document.getElementById("busca-res");
    function norm(s){return String(s).normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase();}
    function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
    function roda(){
      var q=norm(busca.value).trim();
      if(q.length<2){out.innerHTML="";return;}
      var r=idx.filter(function(p){return norm(p[1]+" "+p[2]).indexOf(q)>=0||p[0].indexOf(q)===0;}).slice(0,15);
      out.innerHTML=r.length?"<ul class=\"plain\">"+r.map(function(p){return "<li><a href=\""+p[3]+"\">"+esc(p[1])+"</a> <span class=\"small\">SH4 "+p[0]+"</span></li>";}).join("")+"</ul>":"<p class=\"small\">Nenhum produto encontrado.</p>";
    }
    busca.addEventListener("input",function(){
      if(idx){roda();return;}
      fetch("/assets/busca.json").then(function(r){return r.json();}).then(function(j){idx=j;roda();}).catch(function(){out.innerHTML="<p class=\"small\">A busca não carregou. Tente recarregar a página.</p>";});
    });
  }
  // Copiar texto do resumo
  var cpp=document.getElementById("copy-post");
  if(cpp){cpp.addEventListener("click",function(){
    var t=document.getElementById("post").value,msg=document.getElementById("copy-post-msg");
    try{navigator.clipboard.writeText(t).then(function(){msg.textContent="Texto copiado.";},function(){msg.textContent="Selecione o texto e copie manualmente.";});}catch(e){msg.textContent="Selecione o texto e copie manualmente.";}
  });}
  // Copiar código de incorporação
  var cp=document.getElementById("copy-embed");
  if(cp){cp.addEventListener("click",function(){
    var code=document.getElementById("embed-code").textContent,msg=document.getElementById("copy-msg");
    try{navigator.clipboard.writeText(code).then(function(){msg.textContent="Código copiado.";},function(){msg.textContent="Selecione o código e copie manualmente.";});}catch(e){msg.textContent="Selecione o código e copie manualmente.";}
  });}
})();

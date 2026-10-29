// Comportamentos comuns do MeuBarber, sem JavaScript dentro do HTML
// (a política de segurança da página bloqueia scripts e eventos inline).
//   data-confirmar="pergunta" num <form>: pede confirmação antes de enviar.
//   data-enviar-ao-mudar num campo: envia o formulário quando o valor muda.
document.addEventListener("submit", function (e) {
    var form = e.target.closest("form[data-confirmar]");
    if (form && !window.confirm(form.getAttribute("data-confirmar"))) {
        e.preventDefault();
    }
});
document.addEventListener("change", function (e) {
    if (e.target.hasAttribute && e.target.hasAttribute("data-enviar-ao-mudar") && e.target.form) {
        e.target.form.submit();
    }
});

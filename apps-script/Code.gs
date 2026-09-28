/**
 * Duas Barras · Layout 3D
 * Publica a visualização 3D do barracão como app da Web do Google Apps Script.
 *
 * Arquivos do projeto: Code.gs, Index.html, Layout.html (dados da planta) e Viewer.html (visualizador 3D).
 */
function doGet() {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Duas Barras · Layout 3D')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, viewport-fit=cover')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/** Insere o conteúdo de outro arquivo HTML do projeto (usado em Index.html). */
function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

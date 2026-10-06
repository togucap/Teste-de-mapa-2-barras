/**
 * Casa Jardim Primavera · 3D
 * Publica a visualização 3D da casa (modelo gerado no Blender) como app da Web do Google Apps Script.
 *
 * Arquivos do projeto: Code.gs, Index.html (interface), Viewer.html (visualizador 3D)
 * e Modelo.html (modelo 3D .glb compactado, gerado por tools/build.py).
 */
function doGet() {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Casa Jardim Primavera · 3D')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, viewport-fit=cover')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/** Insere o conteúdo de outro arquivo HTML do projeto (usado em Index.html). */
function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

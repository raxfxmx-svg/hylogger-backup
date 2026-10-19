import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source = "C:/Users/USER/Downloads/gswa-hylogger-2026_07_06.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 14,
  tableMaxCellChars: 120,
});

console.log(overview.ndjson);

const headers = await workbook.inspect({
  kind: "table",
  range: "Sheet1!A1:AC3",
  maxChars: 12000,
  tableMaxRows: 3,
  tableMaxCols: 29,
  tableMaxCellChars: 160,
});
console.log("---HEADERS---");
console.log(headers.ndjson);

const target = await workbook.inspect({
  kind: "match",
  searchTerm: "05GJD001",
  options: { useRegex: false, maxResults: 20 },
  maxChars: 8000,
});
console.log("---TARGET---");
console.log(target.ndjson);

const targetRow = await workbook.inspect({
  kind: "table",
  range: "Sheet1!A27:AC29",
  maxChars: 10000,
  tableMaxRows: 3,
  tableMaxCols: 29,
  tableMaxCellChars: 180,
});
console.log("---TARGET-ROW---");
console.log(targetRow.ndjson);

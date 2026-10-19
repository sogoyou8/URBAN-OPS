// Power BI Desktop -> Transform Data -> New Blank Query -> Advanced Editor.
// Name this query: fxLoadUrbanCSV
// Edit the folder path ONCE here, then invoke it for each exported table.
(tableName as text) as table =>
let
    ExportFolder = "C:\UrbanOps\data\p4-export\",
    CsvSource = Csv.Document(
        File.Contents(ExportFolder & tableName & ".csv"),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]
    ),
    WithHeaders = Table.PromoteHeaders(CsvSource, [PromoteAllScalars=true]),
    // Type inference intentionally disabled: apply declared types in the model.
    Result = WithHeaders
in
    Result
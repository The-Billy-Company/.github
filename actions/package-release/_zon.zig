//! Read the package authority with Zig's ZON parser, including its diagnostics.
const std = @import("std");

pub fn main(init: std.process.Init) !void {
    const arena = init.arena.allocator();
    const args = try init.minimal.args.toSlice(arena);
    if (args.len != 2) return error.ExpectedSourcePath;
    const bytes = try std.Io.Dir.cwd().readFileAlloc(init.io, args[1], arena, .unlimited);
    const source = try arena.dupeZ(u8, bytes);
    var diagnostics: std.zon.parse.Diagnostics = .{};
    const package = std.zon.parse.fromSliceAlloc(struct { version: []const u8 }, arena, source, &diagnostics, .{
        .ignore_unknown_fields = true,
    }) catch |err| {
        std.debug.print("{f}\n", .{diagnostics});
        return err;
    };
    const tree = diagnostics.ast;
    var fields: [2]std.zig.Ast.Node.Index = undefined;
    const root = tree.fullStructInit(&fields, tree.rootDecls()[0]).?;
    var line: usize = 0;
    for (root.ast.fields) |field| {
        const token = tree.firstToken(field) - 2;
        const raw = tree.tokenSlice(token);
        const name = if (std.mem.startsWith(u8, raw, "@\""))
            try std.zig.string_literal.parseAlloc(arena, raw[1..])
        else
            raw;
        if (std.mem.eql(u8, name, "version")) line = tree.tokenLocation(0, token).line + 1;
    }
    var buffer: [256]u8 = undefined;
    var stdout = std.Io.File.stdout().writer(init.io, &buffer);
    try std.json.Stringify.value(.{ .version = package.version, .line = line }, .{}, &stdout.interface);
    try stdout.interface.writeByte('\n');
    try stdout.interface.flush();
}

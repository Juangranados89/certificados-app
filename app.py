<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Resultados</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-gray-900 text-gray-200 flex flex-col items-center py-8">

  <h1 class="text-3xl font-bold mb-5">Resultados</h1>

  <div class="flex gap-4 mb-6">
    <a href="{{ url_for('download_zip') }}"
       class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg font-semibold text-xs">ZIP por nivel</a>
    <a href="{{ url_for('download_excel') }}"
       class="bg-emerald-600 hover:bg-emerald-700 px-4 py-2 rounded-lg font-semibold text-xs">Excel</a>
  </div>

  <div class="w-full max-w-4xl bg-gray-800/70 rounded-xl shadow-xl">
    <div class="overflow-x-auto rounded-xl">
      <table class="min-w-full text-xs">
        <thead class="bg-gray-700 text-gray-400 text-[11px] uppercase tracking-wide">
          <tr>
            <th

<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.1"
	xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
	xmlns:atom="http://www.w3.org/2005/Atom"
	xmlns:atom03="http://purl.org/atom/ns#"
	xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:rssfake="http://purl.org/rss/1.0/"
	>

	<xsl:output method="html"/>

	<xsl:template match="/">
		<html>
		<head>
			<title>RSS feed by morss</title>
			<meta name="viewport" content="width=device-width; initial-scale=1.0; maximum-scale=1.0;" />
			<meta name="robots" content="noindex" />

			<style type="text/css">
				body {
					overflow-wrap: anywhere;
					word-wrap: anywhere;
					font-family: sans;
				}

				input {
					font-family: inherit;
					font-size: inherit;
					text-align: inherit;
				}

				header {
					text-align: center;
					border-bottom: 1px solid silver;
				}

				.input-combo {
					display: flex;
					flex-flow: row;
					align-items: stretch;

					width: 800px;
					max-width: 100%;
					margin: auto;

					border: 1px solid grey;

					padding: .5em .5em;
					background-color: #FFFAF4;
				}

				.input-combo * {
					display: inline-block;
					line-height: 2em;
					border: 0;
					background: transparent;
				}

				.input-combo > :not(.button) {
					max-width: 100%;
					flex-grow: 1;
					flex-shrink 0;

					white-space: nowrap;
					text-overflow: ellipsis;
					overflow: hidden;
				}

				.input-combo .button {
					flex-grow: 0;
					flex-shrink 1;

					cursor: pointer;
					min-width: 2em;
					text-align: center;
					border-left: 1px solid silver;
					color: #06f;
				}

				[onclick_title] {
					cursor: pointer;
					position: relative;
				}

				[onclick_title]::before {
					opacity: 0;

					content: attr(onclick_title);
					font-weight: normal;

					position: absolute;
					left: -300%;

					z-index: 1;

					background: grey;
					color: white;

					border-radius: 0.5em;
					padding: 0 1em;
				}

				[onclick_title]:not(:active)::before {
					transition: opacity 1s ease-in-out;
				}

				[onclick_title]:active::before {
					opacity: 1;
				}

				header > form {
					text-align: center;
					margin: 1%;
				}

				header a {
					text-decoration: inherit;
					color: #FF7B0A;
					font-weight: bold;
				}

				.item {
					background-color: #FFFAF4;
					border: 1px solid silver;
					margin: 1%;
					max-width: 100%;
				}

				.item > * {
					padding: 1%;
				}

				.item > :not(:last-child) {
					border-bottom: 1px solid silver;
				}

				.item > a {

					display: block;
					font-weight: bold;
					font-size: 1.5em;
				}

				.content * {
					max-width: 100%;
				}
			</style>
		</head>

		<body>
			<header>
				<h1>RSS feed by morss</h1>

				<p>Your RSS feed is <strong style="color: green">ready</strong>. You
				can enter the following url in your newsreader:</p>

				<div class="input-combo">
					<input id="url" readonly="readonly"/>
					<span class="button" onclick="copy_link()" title="Copy" onclick_title="Copied">
						<svg width="16px" height="16px" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
							<path fill-rule="evenodd" d="M4 1.5H3a2 2 0 00-2 2V14a2 2 0 002 2h10a2 2 0 002-2V3.5a2 2 0 00-2-2h-1v1h1a1 1 0 011 1V14a1 1 0 01-1 1H3a1 1 0 01-1-1V3.5a1 1 0 011-1h1v-1z" clip-rule="evenodd"/>
							<path fill-rule="evenodd" d="M9.5 1h-3a.5.5 0 00-.5.5v1a.5.5 0 00.5.5h3a.5.5 0 00.5-.5v-1a.5.5 0 00-.5-.5zm-3-1A1.5 1.5 0 005 1.5v1A1.5 1.5 0 006.5 4h3A1.5 1.5 0 0011 2.5v-1A1.5 1.5 0 009.5 0h-3z" clip-rule="evenodd"/>
						</svg>
					</span>
				</div>
			</header>

			<div id="header">
				<h1>
					<xsl:value-of select="rdf:RDF/rssfake:channel/rssfake:title|rss/channel/title|atom:feed/atom:title|atom03:feed/atom03:title"/>
				</h1>

				<p>
					<xsl:value-of select="rdf:RDF/rssfake:channel/rssfake:description|rss/channel/description|atom:feed/atom:subtitle|atom03:feed/atom03:subtitle"/>
				</p>
			</div>

			<div id="content">
				<xsl:for-each select="rdf:RDF/rssfake:channel/rssfake:item|rss/channel/item|atom:feed/atom:entry|atom03:feed/atom03:entry">
					<div class="item">
						<a href="/" target="_blank"><xsl:attribute name="href"><xsl:value-of select="rssfake:link|link|atom:link/@href|atom03:link/@href"/></xsl:attribute>
								<xsl:value-of select="rssfake:title|title|atom:title|atom03:title"/>
						</a>

						<div class="desc">
							<xsl:copy-of select="rssfake:description|description|atom:summary|atom03:summary"/>
						</div>

						<div class="content">
							<xsl:copy-of select="content:encoded|atom:content|atom03:content"/>
						</div>
					</div>
				</xsl:for-each>
			</div>

			<script>
				document.getElementById("url").innerHTML = window.location.href.replace(/:html\/?/, '')

				if (!/:html/.test(window.location.href))
					for (var content of document.querySelectorAll(".desc,.content"))
						content.innerHTML = (content.innerText.match(/>/g) || []).length > 10 ? content.innerText : content.innerHTML

				function copy_content(input) {
					input.focus()
					input.select()
					document.execCommand('copy')
				}

				function copy_link() {
					copy_content(document.getElementById("url"))
				}
			</script>
		</body>
		</html>
	</xsl:template>
</xsl:stylesheet>

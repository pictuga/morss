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

				#url {
					background-color: rgba(255, 165, 0, 0.25);
					padding: 1% 5%;
					display: inline-block;
					max-width: 100%;
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
			<h1>RSS feed by morss</h1>

			<p>Your RSS feed is <strong style="color: green">ready</strong>. You
			can enter the following url in your newsreader:</p>

			<div id="url"></div>

			<hr/>

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
				document.getElementById("url").innerHTML = window.location.href.replace(':html/', '')

				if (!/:html/.test(window.location.href))
					for (var content of document.querySelectorAll(".desc,.content"))
						content.innerHTML = content.children.children ? content.innerHTML : content.innerText
			</script>
		</body>
		</html>
	</xsl:template>
</xsl:stylesheet>

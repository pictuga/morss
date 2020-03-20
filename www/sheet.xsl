<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.1" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

	<xsl:output method="html"/>

	<xsl:template match="/">
		<html>
		<head>
			<title>RSS feed by morss</title>

			<style type="text/css">
				body > pre {
					background-color: #FFFAF4;
					padding: 1%;
					overflow-x: scroll;
					max-width: 100%;
				}

				ul {
					list-style-type: none;
				}

				.element {
					color: darkred;
				}

				.comment {
					color: lightgrey;
				}

				pre {
					margin: 0;
					max-width: 100%;
					white-space: normal;
					overflow-wrap: anywhere;
					word-wrap: anywhere;
				}
			</style>
		</head>

		<body>
			<h1>RSS feed by morss</h1>

			<p>Your RSS feed is <strong style="color: green">ready</strong>. You
			can enter the url of this page in your newsreader.</p>

			<ul>
				<xsl:apply-templates/>
			</ul>

		</body>
		</html>
	</xsl:template>

	<xsl:template match="*">
		<li>
			<span class="element">
				<xsl:value-of select="concat('&lt;', name(), '&gt;')"/>
			</span>
			<xsl:if test="node()">
				<ul>
					<xsl:apply-templates/>
				</ul>
			</xsl:if>
			<span class="element">
				<xsl:value-of select="concat('&lt;/', name(), '&gt;')"/>
			</span>
		</li>
	</xsl:template>

	<xsl:template match="comment()">
		<li>
			<pre class="comment"><![CDATA[<!--]]><xsl:value-of select="."/><![CDATA[-->]]></pre>
		</li>
	</xsl:template>

	<xsl:template match="text()">
		<li>
			<pre>
				<xsl:value-of select="normalize-space(.)"/>
			</pre>
		</li>
	</xsl:template>

	<xsl:template match="text()[not(normalize-space())]"/>

</xsl:stylesheet>

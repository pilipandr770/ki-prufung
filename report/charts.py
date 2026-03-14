import plotly.graph_objects as go
import plotly.express as px
import pandas as pd


def rating_bar_chart(distribution: dict[int, int]) -> str:
    stars = [f"{'★' * s}{'☆' * (5-s)}" for s in range(1, 6)]
    counts = [distribution.get(i, 0) for i in range(1, 6)]
    colors = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#27ae60"]

    fig = go.Figure(go.Bar(
        x=stars,
        y=counts,
        marker_color=colors,
        text=counts,
        textposition="outside",
    ))
    fig.update_layout(
        title="Bewertungsverteilung",
        xaxis_title="Sterne",
        yaxis_title="Anzahl Bewertungen",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial, Helvetica, sans-serif", size=13),
        margin=dict(l=40, r=40, t=50, b=40),
        height=350,
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn", div_id="chart_rating")


def sentiment_pie_chart(distribution: dict[str, int]) -> str:
    labels = list(distribution.keys())
    values = list(distribution.values())
    colors = {"positiv": "#27ae60", "neutral": "#95a5a6", "negativ": "#e74c3c"}
    color_list = [colors.get(l, "#3498db") for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker_colors=color_list,
        hole=0.4,
        textinfo="label+percent",
    ))
    fig.update_layout(
        title="Sentiment-Verteilung",
        font=dict(family="Arial, Helvetica, sans-serif", size=13),
        margin=dict(l=20, r=20, t=50, b=20),
        height=350,
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id="chart_sentiment")


def trait_avg_chart(trait_ratings: dict[str, float]) -> str:
    if not trait_ratings:
        return "<p>Keine Trait-Daten verfügbar.</p>"

    df = pd.DataFrame([
        {"Eigenschaft": t, "Durchschnitt": v}
        for t, v in sorted(trait_ratings.items(), key=lambda x: x[1], reverse=True)
    ])

    fig = px.bar(
        df,
        x="Durchschnitt",
        y="Eigenschaft",
        orientation="h",
        color="Durchschnitt",
        color_continuous_scale=["#e74c3c", "#f1c40f", "#27ae60"],
        range_color=[1, 5],
        text="Durchschnitt",
    )
    fig.update_traces(texttemplate="%{text:.1f} ★", textposition="outside")
    fig.update_layout(
        title="Ø Bewertung nach Persona-Eigenschaft",
        xaxis=dict(range=[0, 5.5], title="Ø Sterne"),
        yaxis_title="",
        plot_bgcolor="white",
        paper_bgcolor="white",
        coloraxis_showscale=False,
        font=dict(family="Arial, Helvetica, sans-serif", size=12),
        margin=dict(l=160, r=60, t=50, b=40),
        height=max(300, len(trait_ratings) * 28 + 80),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id="chart_traits")


def keywords_chart(top_keywords: list[tuple[str, int]]) -> str:
    if not top_keywords:
        return "<p>Keine Keyword-Daten verfügbar.</p>"

    words = [k[0] for k in top_keywords[:15]]
    counts = [k[1] for k in top_keywords[:15]]

    fig = go.Figure(go.Bar(
        x=counts[::-1],
        y=words[::-1],
        orientation="h",
        marker_color="#3498db",
        text=counts[::-1],
        textposition="outside",
    ))
    fig.update_layout(
        title="Häufigste Begriffe in Rezensionen",
        xaxis_title="Häufigkeit",
        yaxis_title="",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial, Helvetica, sans-serif", size=12),
        margin=dict(l=120, r=60, t=50, b=40),
        height=380,
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id="chart_keywords")

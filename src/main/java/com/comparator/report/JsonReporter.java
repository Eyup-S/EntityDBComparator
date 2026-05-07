package com.comparator.report;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.io.File;
import java.io.IOException;

public class JsonReporter {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .enable(SerializationFeature.INDENT_OUTPUT)
            .setSerializationInclusion(JsonInclude.Include.NON_NULL);

    public void write(Object data, String outputPath) throws IOException {
        MAPPER.writeValue(new File(outputPath), data);
        System.out.println("[OK] Output written to: " + outputPath);
    }

    public <T> T read(String inputPath, Class<T> type) throws IOException {
        return MAPPER.readValue(new File(inputPath), type);
    }

    public String toJson(Object data) throws IOException {
        return MAPPER.writeValueAsString(data);
    }
}
